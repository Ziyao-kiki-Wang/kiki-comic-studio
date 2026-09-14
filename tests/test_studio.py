"""Behavioral coverage for uploaded characters, transparent layers, editable bubbles and templates."""

import base64
import copy
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ["COMIC_PROJECTS_DIR"] = str(Path("output/test-bootstrap").resolve())

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from server import store
from server.api import tasks
from server.api.app import create_app
from server.api.routers import projects as project_api
from server.core import bubbles, characters, compose, lettering, scenes, story
from server.core.asset_render import render_asset
from server.core.studio import TEMPLATES
from server.services import assets, image_gen, uploads, llm


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(project_api, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(tasks, "TASKS_FILE", tmp_path / "_tasks.json")
    monkeypatch.setattr(tasks, "_tasks", {})

    def forbidden(*args, **kwargs):
        raise AssertionError("A paid generation call was not expected")

    monkeypatch.setattr(image_gen, "generate", forbidden)
    monkeypatch.setattr(image_gen, "edit", forbidden)
    def prepare(prompt, **kwargs):
        data = json.loads(prompt.split("分镜输入 JSON：\n", 1)[1])
        return {"scene_prompt_en": "Prepared scene illustration", "characters": data["scene"]["characters"]}
    monkeypatch.setattr(llm, "chat_json", prepare)
    pid = "test_project"
    folder = store.init_dirs(pid)
    sb = {
        "project_id": pid,
        "title": "核实身份，再做决定",
        "background_mode": "scene",
        "style": {"style_prompt": "comic", "negative_prompt": "text"},
        "style_id": "commercial_comic",
        "characters": [
            {
                "character_id": "user_01",
                "name": "小王",
                "role": "主人公",
                "english_desc": "reference character",
                "reference_source": "upload",
            }
        ],
        "scenes": [],
    }
    for i in range(1, 4):
        sid = f"scene_{i:02d}"
        sb["scenes"].append(
            {
                "scene_id": sid,
                "location": "大厅",
                "scene_prompt_en": "Two people discuss a phone call",
                "characters": ["user_01"],
                "dialogues": [
                    {"speaker": "user_01", "text": "先别转账，我们核实一下！"}
                ],
                "caption": "接到陌生电话，先通过熟悉的渠道核实身份。",
            }
        )
        Image.new("RGB", (600, 400), "#a8c7e8").save(store.version_path(pid, sid, 1))
        store.register_version(pid, sid, 1)
    Image.new("RGBA", (100, 150), "#4488cc").save(folder / "characters" / "user_01.png")
    store.save_storyboard(pid, sb)
    return pid, sb, folder


@pytest.fixture
def client(project):
    return TestClient(create_app())


def data_url(color="red"):
    out = io.BytesIO()
    Image.new("RGB", (80, 120), color).save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("bad_base64", [False, True])
def test_invalid_image_result_never_replaces_or_creates_cache(
    tmp_path, existing, bad_base64
):
    target = tmp_path / "scene_01_v1.png"
    good = base64.b64decode(data_url().split(",", 1)[1])
    if existing:
        target.write_bytes(good)
    encoded = "broken base64!" if bad_base64 else base64.b64encode(good[:len(good) // 2]).decode()
    result = SimpleNamespace(data=[SimpleNamespace(b64_json=encoded)])
    with pytest.raises(image_gen.InvalidImageError, match="scene_01_v1.png"):
        image_gen._save_result(result, target)
    assert target.exists() is existing
    if existing:
        assert target.read_bytes() == good
    assert not list(tmp_path.glob("*.tmp"))


def test_valid_base64_image_is_saved_unchanged(tmp_path):
    encoded = data_url().split(",", 1)[1]
    target = tmp_path / "versions" / "scene_01_v1.png"
    image_gen._save_result(
        SimpleNamespace(data=[SimpleNamespace(b64_json=encoded)]), target
    )
    assert target.read_bytes() == base64.b64decode(encoded)
    image_gen.validate_image(target)
    assert not list(target.parent.glob("*.tmp"))


@pytest.mark.parametrize("recover", [False, True])
def test_image_url_retries_download_and_preserves_previous_file(tmp_path, monkeypatch, recover):
    target = tmp_path / "scene.png"
    previous = base64.b64decode(data_url("blue").split(",", 1)[1])
    good = base64.b64decode(data_url("red").split(",", 1)[1])
    target.write_bytes(previous)
    attempts = []

    def download(url, timeout):
        attempts.append(url)
        assert timeout > 0
        assert target.read_bytes() == previous
        if len(attempts) == 1:
            raise image_gen.urllib.error.URLError("connection interrupted")
        return io.BytesIO(good if recover else good[:len(good) // 2])

    monkeypatch.setattr(image_gen.urllib.request, "urlopen", download)
    result = SimpleNamespace(data=[SimpleNamespace(url="https://example.invalid/image.png")])
    if recover:
        image_gen._save_result(result, target)
        assert target.read_bytes() == good
        assert len(attempts) == 2
    else:
        with pytest.raises(image_gen.InvalidImageError, match="scene.png"):
            image_gen._save_result(result, target)
        assert target.read_bytes() == previous
        assert len(attempts) == 3
    assert len(set(attempts)) == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_continue_regenerates_only_corrupt_active_scene(project, monkeypatch):
    pid, sb, folder = project
    broken = store.active_raw_path(pid, "scene_01")
    raw = broken.read_bytes()
    broken.write_bytes(raw[:len(raw) // 2])
    damaged = broken.read_bytes()
    unaffected = {
        sid: store.active_raw_path(pid, sid).read_bytes()
        for sid in ("scene_02", "scene_03")
    }
    calls = []

    def generate(prompt, path, **kwargs):
        calls.append(path.name)
        encoded = data_url().split(",", 1)[1]
        image_gen._save_result(SimpleNamespace(data=[SimpleNamespace(b64_json=encoded)]), path)

    monkeypatch.setattr(image_gen, "generate", generate)
    scenes.generate_scenes(pid, sb, {})
    assert calls == ["scene_01_v2.png"]
    assert broken.read_bytes() == damaged
    assert store.active_raw_path(pid, "scene_01").name == "scene_01_v2.png"
    image_gen.validate_image(store.active_raw_path(pid, "scene_01"))
    for sid, content in unaffected.items():
        assert store.active_raw_path(pid, sid).name == f"{sid}_v1.png"
        assert store.active_raw_path(pid, sid).read_bytes() == content


def test_bad_generation_result_does_not_register_version(project, monkeypatch):
    pid, sb, _ = project
    current = store.active_raw_path(pid, "scene_01")
    good = current.read_bytes()
    encoded = base64.b64encode(good[:len(good) // 2]).decode()

    def generate(prompt, path, **kwargs):
        image_gen._save_result(SimpleNamespace(data=[SimpleNamespace(b64_json=encoded)]), path)

    monkeypatch.setattr(image_gen, "generate", generate)
    with pytest.raises(image_gen.InvalidImageError):
        scenes.generate_scene(pid, sb, sb["scenes"][0], {}, force=True)
    assert store.scene_versions(pid, "scene_01") == [1]
    assert store.active_raw_path(pid, "scene_01") == current
    assert current.read_bytes() == good


@pytest.mark.parametrize("color", [(255, 255, 255, 255), (0, 0, 0, 0)])
def test_transparent_output_rejects_opaque_or_empty_image(tmp_path, color):
    target = tmp_path / "scene.png"
    original = base64.b64decode(data_url().split(",", 1)[1])
    target.write_bytes(original)
    buffer = io.BytesIO()
    Image.new("RGBA", (80, 120), color).save(buffer, format="PNG")
    result = SimpleNamespace(data=[SimpleNamespace(
        b64_json=base64.b64encode(buffer.getvalue()).decode()
    )])
    with pytest.raises(image_gen.MissingTransparencyError, match="透明背景"):
        image_gen._save_result(result, target, require_transparency=True)
    assert target.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("method", ["generate", "edit", "edit_fallback"])
def test_image_requests_native_transparency_and_keeps_alpha(tmp_path, monkeypatch, method):
    import httpx

    buffer = io.BytesIO()
    picture = Image.new("RGBA", (80, 120), (40, 20, 60, 0))
    picture.paste((200, 30, 90, 255), (20, 20, 60, 90))
    picture.putpixel((19, 20), (200, 30, 90, 128))
    picture.save(buffer, format="PNG")
    content = buffer.getvalue()
    result = SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(content).decode())])
    calls = []

    def request(**kwargs):
        calls.append(kwargs)
        if method == "edit_fallback" and len(calls) == 1:
            raise image_gen.BadRequestError(
                "moderation_blocked",
                response=httpx.Response(400, request=httpx.Request("POST", "https://example.invalid/images/edits")),
                body={"code": "moderation_blocked"},
            )
        return result

    monkeypatch.setattr(image_gen, "_client", SimpleNamespace(images=SimpleNamespace(generate=request, edit=request)))
    target = tmp_path / "scene.png"
    if method == "generate":
        image_gen.generate("transparent subject", target, background="transparent")
    else:
        reference = tmp_path / "reference.png"
        reference.write_bytes(content)
        image_gen.edit("transparent subject", [reference], target, background="transparent")
        assert all(handle.closed for handle in calls[0]["image"])
    assert len(calls) == (2 if method == "edit_fallback" else 1)
    for call in calls:
        assert call["background"] == "transparent"
        assert call["output_format"] == "png"
    assert target.read_bytes() == content
    assert image_gen.validate_image(target, require_transparency=True)


def test_edit_uses_active_image_and_keeps_versions(project, monkeypatch):
    pid, sb, folder = project
    source = store.active_raw_path(pid, "scene_01")
    old_bytes = source.read_bytes()
    calls = []

    def edit(prompt, refs, out, **kwargs):
        calls.append((prompt, refs, kwargs))
        Image.new("RGB", (600, 400), "white").save(out)

    monkeypatch.setattr(image_gen, "edit", edit)
    scenes.generate_scene(
        pid,
        sb,
        sb["scenes"][0],
        {},
        force=True,
        edit_instruction="保留桌椅，手机自然展示",
    )
    assert calls[0][1][0] == source
    assert "保留桌椅，手机自然展示" in calls[0][0]
    assert calls[0][2]["allow_reference_fallback"] is False
    assert source.read_bytes() == old_bytes
    assert store.active_raw_path(pid, "scene_01").name.endswith("_v2.png")
    assert store.load_scene_meta(pid, "scene_01")["generation_history"]["v2"][
        "edit_instruction"
    ]


def test_failed_edit_keeps_active_version(project, monkeypatch):
    pid, sb, _ = project
    source = store.active_raw_path(pid, "scene_01")

    def fail(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(image_gen, "edit", fail)
    with pytest.raises(RuntimeError):
        scenes.generate_scene(
            pid, sb, sb["scenes"][0], {}, force=True, edit_instruction="调整手机"
        )
    assert store.active_raw_path(pid, "scene_01") == source


def test_download_has_attachment_and_edit_validates(client, project):
    pid, _, _ = project
    response = client.get(f"/api/files/{pid}/versions/scene_01_v1.png?download=true")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert (
        client.post(
            f"/api/projects/{pid}/generate",
            json={"action": "edit_scene", "scene_id": "scene_01", "instruction": "  "},
        ).status_code
        == 422
    )


def test_continue_generates_transparency_for_old_opaque_scenes(project, monkeypatch):
    pid, sb, _ = project
    sb["background_mode"] = "transparent"
    sb["scenes"][2]["background_mode"] = "scene"
    native = store.active_raw_path(pid, "scene_01")
    image = Image.new("RGBA", (600, 400), (20, 30, 40, 0))
    image.paste("white", (50, 80, 550, 350))
    image.save(native)
    before = {s["scene_id"]: store.active_raw_path(pid, s["scene_id"]).read_bytes() for s in sb["scenes"]}
    calls = []

    def generate(prompt, path, **kwargs):
        calls.append((path.name, kwargs))
        image.save(path)

    monkeypatch.setattr(image_gen, "generate", generate)
    scenes.generate_scenes(pid, sb, {})
    assert calls == [("scene_02_v2.png", {"size": "1536x1024", "background": "transparent"})]
    assert store.load_scene_meta(pid, "scene_02")["generation_history"]["v2"]["background"] == "transparent"
    for sid, content in before.items():
        assert store.version_path(pid, sid, 1).read_bytes() == content
    assert store.active_raw_path(pid, "scene_01").name == "scene_01_v1.png"
    assert store.active_raw_path(pid, "scene_03").name == "scene_03_v1.png"


def test_reference_generation_requests_transparent_images_once(project, monkeypatch):
    pid, sb, folder = project
    sb["characters"].append({"character_id": "new_character", "name": "配角", "english_desc": "a comic character"})
    sb["props"] = [{"prop_id": "phone", "name": "手机", "english_desc": "a phone"}]
    supplied = (folder / "characters/user_01.png").read_bytes()
    calls = []

    def generate(prompt, path, **kwargs):
        calls.append(path.name)
        assert kwargs["background"] == "transparent"
        image = Image.new("RGBA", (80, 120), (0, 0, 0, 0))
        image.paste("white", (20, 20, 60, 90))
        image.save(path)

    monkeypatch.setattr(image_gen, "generate", generate)
    refs = characters.generate_references(pid, sb)
    assert calls == ["new_character.png"]
    assert "phone" not in refs and not (folder / "props/phone.png").exists()
    assert (folder / "characters/user_01.png").read_bytes() == supplied
    assert (folder / "characters/new_character_rgba.png").read_bytes() == (folder / "characters/new_character.png").read_bytes()


def test_integrated_phone_skips_separate_generation(project, monkeypatch):
    from server.core import screens

    pid, sb, _ = project
    scene = sb["scenes"][0]
    scene["screen_inset"] = {"screen_prompt_en": "A warning on the screen"}
    screens.generate_screens(pid, sb)  # fixture forbids paid image calls
    lettering.letter_scene(pid, sb, scene, force=True)
    assert "screen_inset" not in store.load_scene_meta(pid, scene["scene_id"])
    prompt = scenes._build_prompt(sb, {**scene, "background_mode": "transparent"})
    assert "Furniture is foreground" in prompt
    assert "A warning on the screen" in prompt


def test_screen_opt_in_controls_prompt_and_cached_inset(project):
    from server.core import screens
    from server.core.studio import screen_enabled

    pid, sb, folder = project
    scene = sb["scenes"][0]
    ordinary = {**scene, "scene_prompt_en": "A girl waters flowers", "screen_mode": "integrated"}
    assert not screen_enabled(ordinary)
    assert "COMPOSITION OVERRIDE" not in scenes._build_prompt(sb, ordinary)
    scene.update(screen_enabled=False, screen_mode="inset", screen_inset={"screen_prompt_en": "OLD SCREEN CONTENT"})
    Image.new("RGB", (100, 160), "red").save(folder / "screens/scene_01_screen.png")
    meta = store.load_scene_meta(pid, "scene_01")
    meta["screen_inset"] = {"x": 10, "y": 10, "width": 100, "height": 160}
    store.save_scene_meta(pid, "scene_01", meta)
    screens.generate_screens(pid, sb)
    lettering.letter_scene(pid, sb, scene, force=True)
    assert "screen_inset" not in store.load_scene_meta(pid, "scene_01")
    assert "OLD SCREEN CONTENT" not in scenes._build_prompt(sb, scene)
    assert "does not need phones" in scenes._build_prompt(sb, scene)


def test_story_setting_changes_update_only_affected_originals(client, project, monkeypatch):
    pid, sb, _ = project
    draft = copy.deepcopy(sb)
    draft["scenes"][0]["screen_enabled"] = False
    draft["scenes"][1]["caption"] = "仅修改旁白"
    assert client.put(f"/api/projects/{pid}/storyboard", json=draft).status_code == 200
    assert store.load_scene_meta(pid, "scene_01")["generation_stale"]
    assert not store.load_scene_meta(pid, "scene_02").get("generation_stale")
    calls = []
    def generate(prompt, out, **kwargs):
        calls.append(out.name)
        Image.new("RGB", (600, 400), "white").save(out)
    monkeypatch.setattr(image_gen, "generate", generate)
    scenes.generate_scenes(pid, store.load_storyboard(pid), {})
    assert calls == ["scene_01_v2.png"]
    assert not store.load_scene_meta(pid, "scene_01")["generation_stale"]
    scenes.generate_scenes(pid, store.load_storyboard(pid), {})
    assert len(calls) == 1
    # The reverse background change also needs a new original, even though
    # a transparent PNG is a valid image for the opaque-mode validator.
    saved = store.load_storyboard(pid)
    saved["background_mode"] = "transparent"
    store.save_storyboard(pid, saved)
    saved["background_mode"] = "scene"
    assert client.put(f"/api/projects/{pid}/storyboard", json=saved).status_code == 200
    assert all(store.load_scene_meta(pid, s["scene_id"])["generation_stale"] for s in saved["scenes"])


def test_screen_description_refreshes_cached_screen(client, project, monkeypatch):
    from server.core import screens

    pid, sb, folder = project
    sb["scenes"][0].update(screen_enabled=True, screen_mode="inset", screen_inset={"screen_prompt_en": "old content"})
    store.save_storyboard(pid, sb)
    Image.new("RGB", (100, 160), "red").save(folder / "screens/scene_01_screen.png")
    sb["scenes"][0]["screen_inset"]["screen_prompt_en"] = "new content"
    assert client.put(f"/api/projects/{pid}/storyboard", json=sb).status_code == 200
    calls = []
    def generate(prompt, out, **kwargs):
        calls.append(prompt)
        Image.new("RGB", (100, 160), "blue").save(out)
    monkeypatch.setattr(image_gen, "generate", generate)
    screens.generate_screens(pid, store.load_storyboard(pid))
    screens.generate_screens(pid, store.load_storyboard(pid))
    assert len(calls) == 1 and "new content" in calls[0]
    assert store.load_scene_meta(pid, "scene_01")["screen_inset_hidden"] is False
    sb["scenes"][0]["screen_inset"]["screen_prompt_en"] = " "
    response = client.put(f"/api/projects/{pid}/storyboard", json=sb)
    assert response.status_code == 422 and "第 1 格" in response.json()["detail"]


def test_bubble_palette_roundtrip_and_paint(client, project):
    pid, _, _ = project
    b = {
        "x": 30,
        "y": 30,
        "width": 300,
        "font_size": 30,
        "text": "你好",
        "type": "cloud",
        "fill": "#e3f2eb",
        "stroke": "#000000",
        "stroke_width": 0,
        "text_color": "#244640",
    }
    assert (
        client.put(
            f"/api/projects/{pid}/scenes/scene_01/layout", json={"bubbles": [b]}
        ).status_code
        == 200
    )
    saved = store.load_scene_meta(pid, "scene_01")["bubbles"][0]
    assert saved["stroke_width"] == 0
    im = Image.new("RGBA", (600, 400))
    bubbles.paint(im, saved, lettering.load_font(30))
    assert (0, 0, 0, 255) not in set(im.getdata())
    bad = {**b, "fill": "url(evil)"}
    assert (
        client.put(
            f"/api/projects/{pid}/scenes/scene_01/layout", json={"bubbles": [bad]}
        ).status_code
        == 422
    )


def test_title_spacing_changes_geometry_without_extra_label(project, client):
    from PIL import ImageChops

    pid, sb, _ = project
    lettering.letter_all(pid, sb)
    first, a = compose.render_long_image(
        pid, sb, {"template_id": "minimal", "title_top": 40}
    )
    second, b = compose.render_long_image(
        pid, sb, {"template_id": "minimal", "title_top": 120}
    )
    assert b["scenes"][0]["y"] - a["scenes"][0]["y"] == 80
    assert second.height - first.height == 80
    assert (
        ImageChops.difference(
            second.crop((0, 0, 1080, 120)), Image.new("RGB", (1080, 120), "white")
        ).getbbox()
        is None
    )
    spaced, _ = compose.render_long_image(
        pid, sb, {"letter_spacing": 10, "body_line_gap": 40, "title_line_gap": 40}
    )
    assert spaced.height > first.height
    assert (
        client.post(
            f"/api/projects/{pid}/long-preview", json={"title_top": 401}
        ).status_code
        == 422
    )


def test_upload_preserves_character_and_requires_confirmation(
    project, client, monkeypatch
):
    pid, sb, folder = project
    response = client.put(
        f"/api/projects/{pid}/characters/user_01/reference",
        json={"name": "既有IP", "role": "主角", "image_data": data_url()},
    )
    assert response.status_code == 200, response.text
    current = store.load_storyboard(pid)
    assert current["characters"][0]["reference_source"] == "upload"
    assert not current["characters_confirmed"]
    assert all(s["stale"] for s in current["scenes"])
    assert len(list((folder / "characters/history").glob("*.png"))) == 1
    assert (
        client.post(
            f"/api/projects/{pid}/generate", json={"action": "run_all"}
        ).status_code
        == 409
    )
    refs = characters.generate_references(pid, current)
    assert refs["user_01"].exists()  # paid calls are forbidden by the fixture
    assert client.post(f"/api/projects/{pid}/characters/confirm").status_code == 200
    assert store.load_storyboard(pid)["characters_confirmed"]
    with pytest.raises(ValueError, match="不会自动重画"):
        characters.generate_references(pid, current, only_character="user_01")


def test_create_supplied_character_is_in_story_prompt(project, client, monkeypatch):
    pid, sb, folder = project
    generated = copy.deepcopy(sb)
    generated["scenes"] = generated["scenes"][:1]
    generated["props"] = [{"prop_id": "phone", "name": "手机", "english_desc": "black phone"}]
    generated["scenes"][0]["props"] = ["phone"]
    prompts = []
    monkeypatch.setattr(
        story.llm, "chat_json", lambda p, **kw: (prompts.append((p, kw)), generated)[1]
    )

    def sync_submit(kind, pid, detail, fn):
        fn()
        return tasks.Task(task_id="test_task", kind=kind, project_id=pid, status="done")

    monkeypatch.setattr(tasks, "submit", sync_submit)
    response = client.post(
        "/api/projects",
        json={
            "topic": "防骗",
            "scene_count": 1,
            "style_id": "commercial_comic",
            "background_mode": "transparent",
            "characters": [
                {"name": "固定主人公", "role": "银行员工", "image_data": data_url()}
            ],
        },
    )
    assert response.status_code == 201, response.text
    created = store.load_storyboard(response.json()["project_id"])
    assert "固定主人公" in prompts[0][0] and "user_01" in prompts[0][0]
    label, image_path = prompts[0][1]["image_refs"][0]
    assert "user_01" in label and "固定主人公" in label
    assert image_path.read_bytes() == uploads.decode_image(data_url())
    assert created["characters"][0]["english_desc"] == "reference character"
    assert created["characters"][0]["name"] == "固定主人公"
    assert created["background_mode"] == "transparent"
    assert created["characters_confirmed"] is False
    assert "props" not in created and "props" not in created["scenes"][0]
    story.prepare_scene_prompt(created["project_id"], created, created["scenes"][0])
    assert len(prompts) == 1  # The initial story already saw these exact references.


def test_llm_sends_labeled_images_and_keeps_text_only_requests(project, monkeypatch):
    _, _, folder = project
    captured = []

    def request(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))])

    monkeypatch.setattr(llm, "_client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=request))))
    reference = folder / "characters/user_01.png"
    llm._request("Observe these identities", 0.2, [("user_01 = A", reference)])
    content = captured[0]["messages"][0]["content"]
    assert content[1] == {"type": "text", "text": "user_01 = A"}
    assert content[2]["type"] == "image_url"
    url = content[2]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == reference.read_bytes()
    llm._request("Text only", 0.7)
    assert captured[1]["messages"][0]["content"] == "Text only"


def test_unsupported_vision_is_not_retried_without_images(project, monkeypatch):
    import httpx
    from openai import BadRequestError
    _, _, folder = project
    calls = []

    def request(**kwargs):
        calls.append(kwargs)
        raise BadRequestError("image input unsupported", response=httpx.Response(
            400, request=httpx.Request("POST", "https://example.invalid/chat/completions")), body=None)

    monkeypatch.setattr(llm, "_client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=request))))
    monkeypatch.setattr(llm, "_supports_reasoning_effort", True)
    with pytest.raises(BadRequestError):
        llm._request("Inspect A", 0.2, [("A", folder / "characters/user_01.png")])
    assert len(calls) == 1
    assert calls[0]["messages"][0]["content"][-1]["type"] == "image_url"


@pytest.mark.parametrize("changed", ["character", "prop", "prop_selection", "style"])
def test_shared_visual_setting_invalidates_affected_scenes(client, project, changed):
    pid, sb, _ = project
    sb["scenes"][1]["characters"] = []
    sb["scenes"][2]["characters"] = []
    sb["props"] = [{"prop_id": "phone", "name": "手机", "english_desc": "black phone"}]
    sb["scenes"][1]["props"] = ["phone"]
    store.save_storyboard(pid, sb)
    draft = copy.deepcopy(sb)
    if changed == "character":
        draft["characters"][0]["role"] = "骗子"
    elif changed == "prop":
        draft["props"][0]["english_desc"] = "red phone"
    elif changed == "prop_selection":
        draft["scenes"][1]["props"] = []
    else:
        draft["style"]["style_prompt"] = "watercolor"
    assert client.put(f"/api/projects/{pid}/storyboard", json=draft).status_code == 200
    affected = [s["scene_id"] for s in sb["scenes"] if (store.load_scene_meta(pid, s["scene_id"]) or {}).get("generation_stale")]
    assert affected == {"character": ["scene_01"], "prop": [], "prop_selection": [], "style": ["scene_01", "scene_02", "scene_03"]}[changed]


def test_cast_and_story_edits_prepare_only_affected_scene(client, project, monkeypatch):
    pid, sb, folder = project
    sb["characters"].append({"character_id": "user_02", "name": "B", "role": "骗子", "english_desc": "blue mascot", "reference_source": "upload"})
    sb["scenes"][0].update(characters=["user_01", "user_02"], scene_prompt_en="OLD: B appears on the phone at the table")
    Image.new("RGB", (40, 40), "blue").save(folder / "characters/user_02.png")
    store.save_storyboard(pid, sb)
    draft = copy.deepcopy(sb)
    draft["scenes"][0].update(characters=["user_01"], story="A站着哭，手机很大，显示系统升级")
    assert client.put(f"/api/projects/{pid}/storyboard", json=draft).status_code == 200
    original_dialogue = copy.deepcopy(draft["scenes"][0]["dialogues"])
    model_calls, image_calls = [], []

    def prepare(prompt, **kwargs):
        model_calls.append((json.loads(prompt.split("分镜输入 JSON：\n", 1)[1]), kwargs))
        return {"scene_prompt_en": "user_01 cries standing beside a huge phone showing 系统升级", "characters": ["user_01"],
                "story": "MODEL MUST NOT REWRITE THIS", "dialogues": []}

    def edit(prompt, refs, out, **kwargs):
        image_calls.append((prompt, refs, out.name))
        Image.new("RGB", (600, 400), "white").save(out)

    monkeypatch.setattr(llm, "chat_json", prepare)
    monkeypatch.setattr(image_gen, "edit", edit)
    refs = {cid: folder / f"characters/{cid}.png" for cid in ("user_01", "user_02")}
    scenes.generate_scenes(pid, store.load_storyboard(pid), refs)
    assert len(model_calls) == len(image_calls) == 1
    assert model_calls[0][0]["scene"]["story"] == draft["scenes"][0]["story"]
    assert [p.name for _, p in model_calls[0][1]["image_refs"]] == ["user_01.png"]
    prompt, attached, name = image_calls[0]
    assert name == "scene_01_v2.png"
    assert attached == [refs["user_01"]]
    assert "OLD:" not in prompt and "B appears" not in prompt
    assert "huge phone" in prompt and "Do not reserve a sidebar" not in prompt
    assert "Story action" not in prompt
    saved = store.load_storyboard(pid)
    assert saved["scenes"][0]["story"] == draft["scenes"][0]["story"]
    assert saved["scenes"][0]["dialogues"] == original_dialogue
    assert saved["scenes"][1:] == draft["scenes"][1:]


def test_prepared_prompt_cache_ignores_lettering_but_observes_visual_changes(project, monkeypatch):
    pid, sb, folder = project
    model_calls = []

    def prepare(prompt, **kwargs):
        model_calls.append(prompt)
        return {"scene_prompt_en": "A prepared camera composition", "characters": ["user_01"]}

    def edit(prompt, refs, out, **kwargs):
        Image.new("RGB", (600, 400), "white").save(out)

    monkeypatch.setattr(llm, "chat_json", prepare)
    monkeypatch.setattr(image_gen, "edit", edit)
    refs = {"user_01": folder / "characters/user_01.png"}
    scene = sb["scenes"][0]
    scenes.generate_scene(pid, sb, scene, refs, force=True)
    scene["caption"] = "只改排版文字"
    scene["dialogues"][0]["text"] = "新台词"
    scenes.generate_scene(pid, sb, scene, refs, force=True)
    assert len(model_calls) == 1
    scene["story"] = "改成举起手机"
    scenes.generate_scene(pid, sb, scene, refs, force=True)
    assert len(model_calls) == 2


@pytest.mark.parametrize("story_changed", [False, True])
def test_direction_refresh_keeps_confirmed_edit_unless_visual_inputs_changed(project, monkeypatch, story_changed):
    pid, sb, _ = project
    scene = sb["scenes"][0]
    scene["story"] = "接到退款电话"
    scene["scene_prompt_en"] = "A shocked character beside a giant phone showing 退款5000块钱"
    source = story._prompt_source(pid, sb, scene)
    source.pop("visual_direction")  # Prepared before the new presentation default.
    meta = store.load_scene_meta(pid, scene["scene_id"])
    meta["prompt_preparation"] = {"source": source}
    instruction = "手机和人物一样大，显示退款5000块钱，表情非常震惊"
    meta["generation_history"] = {"v1": {"edit_instruction": instruction}}
    store.save_scene_meta(pid, scene["scene_id"], meta)
    if story_changed:
        scene["story"] = "角色挂断电话后转身离开，不显示退款界面"
    requests = []

    def prepare(prompt, **kwargs):
        data = json.loads(prompt.split("分镜输入 JSON：\n", 1)[1])
        requests.append(data)
        return {"scene_prompt_en": "A designed composition", "characters": scene["characters"]}

    monkeypatch.setattr(llm, "chat_json", prepare)
    before = copy.deepcopy(scene)
    prepared = story.prepare_scene_prompt(pid, sb, scene)
    assert len(requests) == 1  # New direction invalidates the old prepared prompt.
    assert requests[0].get("confirmed_edit_instruction", "") == ("" if story_changed else instruction)
    assert requests[0]["scene"]["story"] == scene["story"]
    assert [s["scene_id"] for s in requests[0]["neighbor_compositions"]] == ["scene_02"]
    assert scene == before and prepared["scene_prompt_en"] == "A designed composition"


@pytest.mark.parametrize("failure", ["invalid_cast", "empty_prompt", "connection", "image"])
def test_preparation_failure_preserves_user_edits_and_active_image(project, monkeypatch, failure):
    pid, sb, folder = project
    scene = sb["scenes"][0]
    scene["story"] = "保留用户刚保存的剧情"
    store.save_storyboard(pid, sb)
    before = (folder / "storyboard.json").read_bytes()
    old = store.active_raw_path(pid, scene["scene_id"])

    def prepare(*args, **kwargs):
        if failure == "connection":
            raise RuntimeError("story provider unavailable")
        return {"scene_prompt_en": "" if failure == "empty_prompt" else "NEW DESCRIPTION",
                "characters": ["invented"] if failure == "invalid_cast" else ["user_01"]}

    def edit(*args, **kwargs):
        raise RuntimeError("image provider unavailable")

    monkeypatch.setattr(llm, "chat_json", prepare)
    monkeypatch.setattr(image_gen, "edit", edit)
    with pytest.raises((ValueError, RuntimeError)):
        scenes.generate_scene(pid, sb, scene, {"user_01": folder / "characters/user_01.png"}, force=True)
    assert (folder / "storyboard.json").read_bytes() == before
    assert scene["scene_prompt_en"] == "Two people discuss a phone call"
    assert store.active_raw_path(pid, scene["scene_id"]) == old
    assert store.scene_versions(pid, scene["scene_id"]) == [1]


def test_edit_removes_character_from_image_references_after_preparation(project, monkeypatch):
    pid, sb, folder = project
    sb["characters"].append({"character_id": "user_02", "name": "B", "role": "骗子", "english_desc": "blue mascot"})
    scene = sb["scenes"][0]
    scene["characters"] = ["user_01", "user_02"]
    Image.new("RGB", (40, 40), "blue").save(folder / "characters/user_02.png")
    store.save_storyboard(pid, sb)
    calls = []
    monkeypatch.setattr(llm, "chat_json", lambda *a, **kw: {"scene_prompt_en": "Only user_01 with the phone", "characters": ["user_01"]})

    def edit(prompt, refs, out, **kwargs):
        calls.append((prompt, [p.name for p in refs]))
        Image.new("RGB", (600, 400), "white").save(out)

    monkeypatch.setattr(image_gen, "edit", edit)
    refs = {cid: folder / f"characters/{cid}.png" for cid in ("user_01", "user_02")}
    scenes.generate_scene(pid, sb, scene, refs, force=True, edit_instruction="只保留 A")
    assert calls[0][1] == ["scene_01_v1.png", "user_01.png"]
    assert "Image 2 = user_01" in calls[0][0] and "Image 3 = user_02" not in calls[0][0]
    assert store.load_storyboard(pid)["scenes"][0]["characters"] == ["user_01"]


def test_scene_objects_follow_story_without_legacy_prop_selection_or_images(project, monkeypatch):
    pid, sb, folder = project
    sb["style_id"] = "chibi"
    sb["style"] = story.load_style("chibi")
    sb["props"] = [
        {"prop_id": "phone", "name": "手机", "english_desc": "black smartphone"},
        {"prop_id": "old_phone", "name": "旧手机", "english_desc": "legacy pink phone",
         "reference_prompt_version": 2, "reference_description": "legacy pink phone"},
    ]
    legacy = folder / "props/old_phone.png"
    Image.new("RGB", (40, 40), "pink").save(legacy)
    old_bytes = legacy.read_bytes()
    # Even a previously approved object reference must not trigger generation
    # or enter the scene. The fixture rejects all unexpected image API calls.
    refs = characters.generate_references(pid, sb)
    assert set(refs) == {"user_01"}
    assert not (folder / "props/phone.png").exists()
    refs["old_phone"] = legacy  # Also exercise callers that still supply old refs.
    scene = sb["scenes"][0]
    scene["props"] = ["phone", "old_phone"]
    scene["retained_props"] = "legacy pink phone"
    scene["location"] = "社区宣传台"
    scene["story"] = "小王在小桌旁拿起宣传单阅读"
    scene["background_mode"] = "transparent"
    requests = []

    def prepare(prompt, **kwargs):
        data = json.loads(prompt.split("分镜输入 JSON：\n", 1)[1])
        requests.append((data, kwargs))
        return {"scene_prompt_en": "user_01 reads a flyer beside a small table", "characters": ["user_01"]}

    def edit(prompt, files, out, **kwargs):
        assert files == [refs["user_01"]]
        assert "reads a flyer beside a small table" in prompt
        assert "legacy pink phone" not in prompt
        assert "no text" not in prompt and "no words" not in prompt
        assert "big head small body" not in prompt
        im = Image.new("RGBA", (600, 400))
        im.paste("green", (200, 100, 400, 300))
        im.save(out)

    monkeypatch.setattr(llm, "chat_json", prepare)
    monkeypatch.setattr(image_gen, "edit", edit)
    scenes.generate_scene(pid, sb, scene, refs, force=True)
    data, kwargs = requests[0]
    assert data["scene"]["story"] == "小王在小桌旁拿起宣传单阅读"
    assert data["scene"]["location"] == "社区宣传台"
    assert "props" not in data and "props" not in data["scene"] and "retained_props" not in data["scene"]
    assert [path for label, path in kwargs["image_refs"]] == [refs["user_01"]]
    assert legacy.read_bytes() == old_bytes
    assert store.load_storyboard(pid)["props"] == sb["props"]
    assert scenes._ref_files(pid, sb, scene, refs) == [refs["user_01"]]
    scene["props"] = []
    sb["props"][0]["english_desc"] = "red phone"
    story.prepare_scene_prompt(pid, sb, scene)
    assert len(requests) == 1  # Legacy prop edits do not invalidate preparation.


def test_bad_upload_and_traversal_are_rejected(project, client):
    pid, sb, folder = project
    for value in [
        "data:image/svg+xml;base64,AA==",
        "data:image/png;base64,aaaa",
        "hello",
    ]:
        response = client.put(
            f"/api/projects/{pid}/characters/user_01/reference",
            json={"name": "x", "image_data": value},
        )
        assert response.status_code == 422
    with pytest.raises(ValueError):
        store.project_dir("../outside")
    assert client.get(f"/api/files/{pid}/%2e%2e/storyboard.json").status_code == 404


def test_burst_has_no_tail_and_other_shapes_support_it():
    base = {
        "text": "这竟然是骗局！",
        "x": 50,
        "y": 40,
        "width": 420,
        "font_size": 36,
        "tail_tip": {"x": 990, "y": 950},
    }
    for kind in ("burst", "caption"):
        g = bubbles.geometry({**base, "type": kind}, lettering.load_font(36))
        assert not g["circles"]
        assert max(y for x, y in g["points"]) <= g["height"] + 0.001
    for kind in ("speech", "ellipse", "thought", "whisper"):
        g = bubbles.geometry({**base, "type": kind}, lettering.load_font(36))
        assert g["circles"] or [940, 910] in g["points"]


def test_layout_saves_text_geometry_and_inset_deletion(project, client):
    pid, sb, folder = project
    lettering.letter_all(pid, sb)
    b = store.load_scene_meta(pid, "scene_01")["bubbles"][0]
    b.update({"text": "真的？\n先等等！", "type": "burst", "x": 140, "y": 100})
    b.pop("geometry", None)
    b["geometry"] = bubbles.geometry(b, lettering.load_font(b["font_size"]))
    response = client.put(
        f"/api/projects/{pid}/scenes/scene_01/layout",
        json={"bubbles": [b], "screen_inset": None, "caption": "新的旁白"},
    )
    assert response.status_code == 200, response.text
    saved = store.load_storyboard(pid)
    assert saved["scenes"][0]["dialogues"][0]["text"] == b["text"]
    lettering.letter_scene(pid, saved, saved["scenes"][0], force=True)
    meta = store.load_scene_meta(pid, "scene_01")
    assert meta["bubbles"][0]["geometry"] == b["geometry"]
    assert meta["screen_inset_hidden"] and "screen_inset" not in meta
    assert meta["caption"]["text"] == "新的旁白"


def test_independent_text_alignment_and_rotated_bubble():
    font = lettering.load_font(30)
    b = {"x": 120, "y": 80, "width": 260, "body_height": 120, "font_size": 30, "type": "caption", "text": "对齐\n文字框",
         "rotation": 25, "scale_x": 1.4, "scale_y": 0.6,
         "text_box": {"x": 500, "y": 300, "width": 240, "rotation": -15}}
    positions = []
    for align in ("left", "center", "right"):
        g = bubbles.geometry({**b, "text_align": align}, font)
        positions.append(g["lines"][0]["x"])
        im = Image.new("RGBA", (900, 650))
        bubbles.paint(im, {**b, "text_align": align}, font)
        assert im.crop((480, 220, 820, 400)).getbbox()  # independent text is rendered
        assert im.crop((60, 60, 480, 240)).getbbox()  # rotated shell is rendered
    assert positions[0] == 0 < positions[1] < positions[2]
    moved = bubbles.geometry({**b, "x": 210, "y": 150, "rotation": 70}, font)
    assert moved["text_box"] == g["text_box"]
    point = [75, 42]
    assert bubbles.untransform_point(bubbles.transform_point(point, b), b) == pytest.approx(point)


def test_movable_caption_and_single_scene_save(client, project):
    from server.api.routers.generate import _build_fn, GenerateIn
    pid, sb, folder = project
    cap = {"x": 530, "y": 360, "width": 350, "font_size": 30, "align": "right", "rotation": 12}
    response = client.put(f"/api/projects/{pid}/scenes/scene_01/layout", json={"caption_layout": cap})
    assert response.status_code == 200, response.text
    # Saving one scene succeeds while other panels have never been composed.
    _build_fn(pid, GenerateIn(action="recompose_scene", scene_id="scene_01"))()
    meta = store.load_scene_meta(pid, "scene_01")
    assert meta["caption_layout"] == cap and not meta["render_stale"]
    assert not (folder / "output/scene_02.png").exists()
    with Image.open(folder / "output/scene_01.png") as complete, Image.open(folder / "output/scene_01_panel.png") as panel:
        assert complete.tobytes() == panel.tobytes()  # moved caption travels with panel
    lettering.letter_all(pid, store.load_storyboard(pid))
    for template in TEMPLATES:
        image, _ = compose.render_long_image(pid, store.load_storyboard(pid), {"template_id": template})
        assert image.width == 1080
    # Reset remains backwards compatible with the original caption strip.
    assert client.put(f"/api/projects/{pid}/scenes/scene_01/layout", json={"caption_layout": None}).status_code == 200
    _build_fn(pid, GenerateIn(action="recompose_scene", scene_id="scene_01"))()
    assert "caption_layout" not in store.load_scene_meta(pid, "scene_01")
    with Image.open(folder / "output/scene_01.png") as complete, Image.open(folder / "output/scene_01_panel.png") as panel:
        assert complete.height > panel.height


@pytest.mark.parametrize("patch", [{"text_align":"diagonal"}, {"scale_x":0}, {"rotation":999}, {"text_box":{"x":0,"y":0,"width":0}}])
def test_invalid_independent_bubble_controls_rejected(project, client, patch):
    pid, sb, folder = project
    b = {"x":30,"y":30,"width":420,"font_size":36,"text":"台词",**patch}
    assert client.put(f"/api/projects/{pid}/scenes/scene_01/layout", json={"bubbles":[b]}).status_code == 422


def test_transparent_layer_is_versioned_and_keeps_alpha(project, client):
    pid, sb, folder = project
    sb["background_mode"] = "transparent"
    store.save_storyboard(pid, sb)
    raw = store.active_raw_path(pid, "scene_01")
    im = Image.new("RGBA", (600, 400), (20, 30, 40, 0))
    im.paste((220, 30, 30, 255), (200, 100, 400, 350))
    im.paste((255, 255, 255, 255), (0, 120, 200, 200))  # white prop touching border
    im.save(raw)
    original = raw.read_bytes()
    scene = sb["scenes"][0]
    lettering.letter_scene(pid, sb, scene, force=True)
    lettering.letter_scene(pid, sb, scene, force=True)
    assert scenes.scene_asset(pid, sb, scene) == raw
    assert raw.read_bytes() == original
    assert not list((folder / "foreground").iterdir())
    details = client.get(f"/api/projects/{pid}").json()
    first = details["scenes"][0]
    assert first["foreground_url"] == first["raw_url"]
    assert client.get(first["foreground_url"]).content == original
    assert details["scenes"][1]["foreground_url"] is None
    with pytest.raises(image_gen.MissingTransparencyError, match="生成漫画"):
        scenes.scene_asset(pid, sb, sb["scenes"][1])
    with Image.open(folder / "output/scene_01_panel.png") as image:
        assert image.mode == "RGBA" and image.getpixel((0, 0))[3] == 0
    im.save(store.version_path(pid, "scene_01", 2))
    store.register_version(pid, "scene_01", 2)
    assert scenes.scene_asset(pid, sb, scene) == store.version_path(pid, "scene_01", 2)
    store.rollback(pid, "scene_01", 1)
    assert scenes.scene_asset(pid, sb, scene).name == "scene_01_v1.png"
    assert "BACKGROUND OVERRIDE" in scenes._build_prompt(sb, scene)
    assert "immutable designs" in scenes._build_prompt(sb, scene)


@pytest.mark.parametrize("template", [key for key, value in TEMPLATES.items() if not value.get("layout")])
def test_all_templates_render_and_use_individual_gaps(project, template):
    pid, sb, folder = project
    lettering.letter_all(pid, sb)
    img, layout = compose.render_long_image(
        pid,
        sb,
        {
            "template_id": template,
            "gap": 40,
            "gaps": {"scene_01": 120},
            "footer": "先核实再行动。",
        },
    )
    assert img.width == 1080 and img.height == layout["height"]
    a, b, c = layout["scenes"]
    assert [box["heading"]["lines"] for box in (a, b, c)] == [["大厅"]] * 3
    assert b["y"] - a["y"] - a["height"] == 120
    assert c["y"] - b["y"] - b["height"] == 40
    zero, z = compose.render_long_image(
        pid, sb, {"template_id": template, "gap": 0, "gaps": {}}
    )
    assert z["scenes"][1]["y"] == z["scenes"][0]["y"] + z["scenes"][0]["height"]


@pytest.mark.parametrize("template", [key for key, value in TEMPLATES.items() if value.get("layout")])
@pytest.mark.parametrize("count", [1, 5])
def test_creative_pages_keep_scene_order_full_panels_and_footer(project, client, template, count):
    pid, sb, folder = project
    source = copy.deepcopy(sb["scenes"][0])
    sb["scenes"] = []
    for index in range(count):
        scene = {**source, "scene_id": f"scene_{index+1:02d}", "heading": "签字之前先核实"}
        sb["scenes"].append(scene)
        size = (600, 400) if index % 2 == 0 else (300, 500)
        panel = Image.new("RGBA", size, (0,0,0,0))
        # The complete image, including its colored corners, must survive fitting.
        from PIL import ImageDraw
        draw = ImageDraw.Draw(panel)
        draw.rectangle((0,0,40,40),fill="red")
        draw.rectangle((size[0]-41,size[1]-41,size[0]-1,size[1]-1),fill="blue")
        panel.save(folder / "output" / f"{scene['scene_id']}_panel.png")
        if index == 1:
            store.save_scene_meta(pid, scene["scene_id"], {"caption_layout":{"x":0,"y":300}})
    record = assets.create_asset(pid, data_url("green"), kind="image")
    options = {"template_id":template, "gap":48, "gaps":{"scene_01":90}, "body_line_gap":14.5,
               "heading":{"style":"wave","font_size":40},
               "footer_blocks":[{"type":"text","text":"先核实，再决定。"},
                                {"type":"image","asset_id":record["asset_id"],"width":200}]}
    sb["long_layout"] = options
    store.save_storyboard(pid, sb)
    image, layout = compose.render_long_image(pid, sb)
    boxes = layout["scenes"]
    assert [box["scene_id"] for box in boxes] == [scene["scene_id"] for scene in sb["scenes"]]
    for index, box in enumerate(boxes):
        picture, heading = box["picture"], box["heading"]
        assert 0 <= box["x"] < box["x"]+box["width"] <= 1080
        assert box["y"] <= picture["y"] < picture["y"]+picture["height"] <= box["y"]+box["height"]
        assert heading["x"] >= box["x"] and heading["y"]+heading["height"] <= box["y"]+box["height"]
        ratio = 1.5 if index % 2 == 0 else .6
        assert abs(picture["width"] / picture["height"] - ratio) < .02
        assert image.getpixel((picture["x"]+2,picture["y"]+2)) == (255,0,0)
        assert image.getpixel((picture["x"]+picture["width"]-3,picture["y"]+picture["height"]-3)) == (0,0,255)
    if count > 1:
        assert boxes[1]["caption"]["lines"] == []
        if template == "editorial_mix":
            assert boxes[0]["picture"]["x"] < boxes[0]["heading"]["x"]
            assert boxes[1]["picture"]["x"] > boxes[1]["heading"]["x"]
        elif template == "magazine_grid":
            assert boxes[0]["width"] > boxes[1]["width"] and boxes[1]["row"] == boxes[2]["row"]
        elif template == "comic_strip":
            assert boxes[0]["row"] == boxes[1]["row"] == boxes[2]["row"]
        else:
            assert boxes[0]["row"] == boxes[1]["row"]
        for row in range(max(box["row"] for box in boxes)):
            current = [box for box in boxes if box["row"] == row]
            following = [box for box in boxes if box["row"] == row+1]
            assert min(b["y"] for b in following) - max(b["y"]+b["height"] for b in current) == current[0]["gap_after"]
    assert layout["footer_blocks"][0]["y"] > max(box["y"]+box["height"] for box in boxes)
    footer_image = layout["footer_blocks"][1]
    assert footer_image["y"]+footer_image["height"] < image.height
    assert client.post(f"/api/projects/{pid}/long-preview", json=options).status_code == 200


def test_preview_is_read_only_and_validates_settings(project, client):
    pid, sb, folder = project
    lettering.letter_all(pid, sb)
    before = (folder / "storyboard.json").read_bytes()
    response = client.post(
        f"/api/projects/{pid}/long-preview",
        json={"template_id": "qa", "gap": 80, "gaps": {}},
    )
    assert (
        response.status_code == 200 and response.headers["content-type"] == "image/png"
    )
    assert (folder / "storyboard.json").read_bytes() == before
    assert (
        client.post(
            f"/api/projects/{pid}/long-preview", json={"template_id": "unknown"}
        ).status_code
        == 422
    )
    assert (
        client.post(f"/api/projects/{pid}/long-preview", json={"gap": -1}).status_code
        == 422
    )
    assert {t["id"] for t in client.get("/api/styles").json()["templates"]} == set(
        TEMPLATES
    )


def test_heading_styles_wrap_and_preserve_transparent_backgrounds():
    from server.core.headings import render_heading
    from server.core.studio import HEADING_STYLES

    font = lettering.load_font(48)
    for style_id, spec in HEADING_STYLES.items():
        result = render_heading("先停一下，再核实身份", {"style": style_id, "font_size": 48}, font, 330, "#2b7062", 3)
        assert result["width"] <= 330 and len(result["lines"]) > 1
        image = result["image"]
        assert image.mode == "RGBA" and image.getchannel("A").getextrema() == (0, 255)
        # The left padding belongs to the badge background, not to the text.
        assert bool(image.getpixel((40, image.height // 2))[3]) if spec["background"] else image.getpixel((0, 50))[3] == 0


def test_heading_overrides_save_preview_and_hide_independently(client, project):
    pid, sb, _ = project
    lettering.letter_all(pid, sb)
    options = {
        "heading": {"style": "candy", "font_size": 36, "align": "center"},
        "heading_overrides": {
            "scene_02": {"style": "wave", "font_size": 64, "text": "这个小标题很长，需要自动换行，让图片依然显示在标题下方。", "align": "right"},
            "scene_03": {"text": ""},
        },
    }
    sb["long_layout"] = options
    saved = client.put(f"/api/projects/{pid}/storyboard", json=sb)
    assert saved.status_code == 200, saved.text
    loaded = store.load_storyboard(pid)
    assert loaded["long_layout"] == options
    _, layout = compose.render_long_image(pid, loaded)
    a, b, c = layout["scenes"]
    assert a["heading"]["text"] == "大厅" and a["heading"]["style"] == "candy"
    assert abs(a["heading"]["x"] + a["heading"]["width"] / 2 - a["x"] - a["width"] / 2) <= 1
    assert b["heading"]["font_size"] == 64 and len(b["heading"]["lines"]) > 1
    assert b["heading"]["x"] + b["heading"]["width"] == b["x"] + b["width"] - 22
    assert b["height"] > a["height"]
    assert c["heading"]["height"] == 0 and c["height"] < a["height"]
    assert client.post(f"/api/projects/{pid}/long-preview", json=options).status_code == 200
    for patch in [
        {"heading": {"style": "missing"}}, {"heading": {"font_size": 100}},
        {"heading": {"fill": "pink"}}, {"heading_overrides": {"missing_scene": {"style": "wave"}}},
    ]:
        assert client.post(f"/api/projects/{pid}/long-preview", json=patch).status_code == 422


def test_running_task_blocks_conflicting_edit(project, client):
    pid, sb, folder = project
    tasks._tasks["busy"] = tasks.Task(
        task_id="busy", kind="generate", project_id=pid, status="running"
    )
    assert client.put(f"/api/projects/{pid}/storyboard", json=sb).status_code == 409
    assert client.get(f"/api/projects/{pid}").json()["active_task"]["task_id"] == "busy"


def test_changed_text_requires_render_and_pipeline_refreshes_cache(project, client):
    pid, sb, folder = project
    lettering.letter_all(pid, sb)
    meta = store.load_scene_meta(pid, "scene_01")
    b = {**meta["bubbles"][0], "text": "修改后的台词"}
    response = client.put(
        f"/api/projects/{pid}/scenes/scene_01/layout", json={"bubbles": [b]}
    )
    assert response.status_code == 200, response.text
    changed = store.load_storyboard(pid)
    with pytest.raises(ValueError, match="重新合成"):
        compose.render_long_image(pid, changed)
    lettering.letter_all(pid, changed)
    assert not store.load_scene_meta(pid, "scene_01")["render_stale"]
    image, layout = compose.render_long_image(pid, changed)
    assert image.width == 1080
    assert (
        store.load_scene_meta(pid, "scene_01")["bubbles"][0]["geometry"]["input"][
            "text"
        ]
        == "修改后的台词"
    )


def test_malformed_layout_is_rejected_before_saving(project, client):
    pid, sb, folder = project
    lettering.letter_all(pid, sb)
    b = store.load_scene_meta(pid, "scene_01")["bubbles"][0]
    before = (folder / "storyboard.json").read_bytes()
    for patch in [
        {"tail_position": "left"},
        {"tail_tip": {}},
        {"geometry": {"points": [1, 2, 3], "lines": []}},
    ]:
        response = client.put(
            f"/api/projects/{pid}/scenes/scene_01/layout",
            json={"bubbles": [{**b, **patch}]},
        )
        assert response.status_code == 422, response.text
    assert (
        client.post(
            f"/api/projects/{pid}/long-preview", json={"accent": 123}
        ).status_code
        == 422
    )
    assert (folder / "storyboard.json").read_bytes() == before


def test_uploaded_layer_preserves_alpha_and_rotates_around_center(project):
    pid, _, _ = project
    source = io.BytesIO()
    Image.new("RGBA", (10, 4), (255, 0, 0, 128)).save(source, "PNG")
    encoded = "data:image/png;base64," + base64.b64encode(source.getvalue()).decode()
    record = assets.create_asset(pid, encoded, kind="sticker", filename="half.png")

    rgba = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    render_asset(
        rgba,
        pid,
        {
            "asset_id": record["asset_id"],
            "x": 15,
            "y": 18,
            "width": 10,
            "height": 4,
            "rotation": 90,
        },
    )
    # Positive browser rotation is clockwise and expands around (20, 20), so
    # the vertical layer is centered instead of rotating from its top-left.
    bbox = rgba.getchannel("A").getbbox()
    assert bbox is not None and 17 <= bbox[0] <= 18 and 15 <= bbox[1] <= 16
    assert 20 <= bbox[2] <= 23 and 24 <= bbox[3] <= 26
    assert rgba.getpixel((20, 20))[3] == 128

    rgb = Image.new("RGB", (40, 40), "white")
    render_asset(
        rgb,
        pid,
        {"asset_id": record["asset_id"], "x": 15, "y": 18, "width": 10, "height": 4},
    )
    assert rgb.getpixel((16, 19))[0] == 255
    assert 110 <= rgb.getpixel((16, 19))[1] <= 145


def test_shared_font_library_available_without_project_upload(project, client):
    pid, _, folder = project
    rows = client.get(f"/api/projects/{pid}/fonts").json()["fonts"]
    assert len(rows) == 17
    assert all(row["installed"]["source"] == "shared" for row in rows)
    assert not list((folder / "fonts").iterdir())
    for row in rows:
        selected = lettering.load_font(24, pid, row["id"])
        assert Path(selected.path).is_relative_to(assets.FONT_LIBRARY_DIR)
        assert selected.getlength("漫画字体测试") > 0
    sample = next(row for row in rows if row["id"] == "microsoft_yahei_regular")
    response = client.get(sample["installed"]["url"], headers={"Range": "bytes=0-3"})
    assert response.status_code == 206
    assert response.headers["content-type"] == "font/ttf"
    assert response.content == b"\x00\x01\x00\x00"
    assert client.get(f"/api/projects/{pid}/fonts/unknown/file").status_code == 404


def test_font_upload_rejects_invalid_and_loads_selected_slot(project, client):
    pid, sb, _ = project
    bad = client.post(
        f"/api/projects/{pid}/fonts/source_han_sans_regular",
        json={"name": "bad.ttf", "font_data": "data:font/ttf;base64,AAAA"},
    )
    assert bad.status_code == 422

    font_path = Path(__file__).parents[1] / "references" / "StoryDiffusion" / "fonts" / "Inkfree.ttf"
    font_data = "data:font/ttf;base64," + base64.b64encode(font_path.read_bytes()).decode()
    good = client.post(
        f"/api/projects/{pid}/fonts/source_han_sans_regular",
        json={"name": "Inkfree.ttf", "font_data": font_data},
    )
    assert good.status_code == 201, good.text
    override = good.json()["font"]["installed"]
    assert override["source"] == "project"
    assert client.get(override["url"]).content == font_path.read_bytes()
    selected = lettering.load_font(24, pid, "source_han_sans_regular")
    assert Path(selected.path).name == "source_han_sans_regular.ttf"

    sb["scenes"][0]["bubble_font_id"] = "source_han_sans_regular"
    store.save_storyboard(pid, sb)
    lettering.letter_scene(pid, sb, sb["scenes"][0], force=True)
    assert store.load_scene_meta(pid, "scene_01")["bubbles"][0]["font_id"] == "source_han_sans_regular"
    sb["long_layout"] = {
        "template_id": "minimal",
        "title": "字体测试",
        "title_font_id": "source_han_sans_regular",
        "font_size": 42,
    }
    lettering.letter_all(pid, sb)
    picture, _ = compose.render_long_image(pid, sb)
    assert picture.width == 1080
    changed = client.post(
        f"/api/projects/{pid}/fonts/source_han_sans_regular",
        json={"name": "Inkfree.ttf", "font_data": font_data},
    )
    assert changed.status_code == 201
    stale_meta = store.load_scene_meta(pid, "scene_01")
    assert stale_meta["render_stale"] is True
    assert "geometry" not in stale_meta["bubbles"][0]
    assert store.load_storyboard(pid)["scenes"][0]["font_stale"] is True


def test_scene_local_replacement_only_changes_that_scene_generation_refs(project, client, monkeypatch):
    pid, sb, folder = project
    response = client.post(
        f"/api/projects/{pid}/assets",
        json={"name": "official.png", "image_data": data_url("purple"), "kind": "scene_reference"},
    )
    assert response.status_code == 201
    aid = response.json()["asset_id"]
    saved = client.put(
        f"/api/projects/{pid}/scenes/scene_01/references",
        json={
            "references": [
                {"asset_id": aid, "mode": "replace_character", "replace_character_id": "user_01"}
            ]
        },
    )
    assert saved.status_code == 200
    assert store.load_storyboard(pid)["scenes"][0]["reference_stale"] is True
    assert not store.load_scene_meta(pid, "scene_01").get("render_stale", False)

    calls = []

    def fake_edit(prompt, refs, out, **kwargs):
        calls.append(([Path(item).name for item in refs], prompt, kwargs))
        Image.new("RGB", (600, 400), "white").save(out)

    monkeypatch.setattr(image_gen, "edit", fake_edit)
    scene1 = store.load_storyboard(pid)["scenes"][0]
    scenes.generate_scene(pid, store.load_storyboard(pid), scene1, {"user_01": folder / "characters" / "user_01.png"}, force=True)
    assert calls[-1][0] == [f"{aid}.png"]
    assert "appearance exclusively from the scene-specific reference" in calls[-1][1]
    assert calls[-1][2]["allow_reference_fallback"] is False

    scene2 = store.load_storyboard(pid)["scenes"][1]
    scenes.generate_scene(pid, store.load_storyboard(pid), scene2, {"user_01": folder / "characters" / "user_01.png"}, force=True)
    assert calls[-1][0] == ["user_01.png"]
    # The fixture's global character is an uploaded IP reference, so this
    # scene also correctly disables reference fallback even without a local
    # replacement.
    assert calls[-1][2]["allow_reference_fallback"] is False


def test_overlays_and_long_stickers_roundtrip_and_empty_preview_is_clean(project, client):
    pid, sb, folder = project
    uploaded = client.post(
        f"/api/projects/{pid}/assets",
        json={"name": "badge.png", "image_data": data_url("red"), "kind": "sticker"},
    )
    assert uploaded.status_code == 201
    aid = uploaded.json()["asset_id"]
    overlay = {
        "asset_id": aid,
        "x": 40,
        "y": 40,
        "width": 80,
        "height": 120,
        "rotation": 0,
        "opacity": 1,
        "flip_x": False,
        "flip_y": False,
        "z_index": 3,
    }
    saved = client.put(
        f"/api/projects/{pid}/scenes/scene_01/layout", json={"overlays": [overlay]}
    )
    assert saved.status_code == 200
    lettering.letter_scene(pid, store.load_storyboard(pid), store.load_storyboard(pid)["scenes"][0], force=True)
    with Image.open(folder / "output" / "scene_01_panel.png") as panel:
        assert panel.getpixel((50, 50))[0] > 200 and panel.getpixel((50, 50))[1] < 80

    current = copy.deepcopy(store.load_storyboard(pid))
    current["long_layout"] = {
        "template_id": "minimal",
        "stickers": [{**overlay, "x": 20, "y": 16, "width": 40, "height": 60}],
    }
    assert client.put(f"/api/projects/{pid}/storyboard", json=current).status_code == 200
    reloaded = store.load_storyboard(pid)
    assert reloaded["long_layout"]["stickers"][0]["asset_id"] == aid
    lettering.letter_all(pid, reloaded)
    composed, _ = compose.render_long_image(pid, reloaded)
    assert composed.getpixel((22, 18))[0] > 200 and composed.getpixel((22, 18))[1] < 80

    preview = client.post(
        f"/api/projects/{pid}/long-preview", json={"template_id": "minimal", "stickers": []}
    )
    assert preview.status_code == 200
    with Image.open(io.BytesIO(preview.content)) as image:
        assert image.getpixel((22, 18))[0] < 240 or image.getpixel((22, 18))[1] > 80


def test_referenced_asset_cannot_be_deleted_until_layout_reference_removed(project, client):
    pid, _, _ = project
    uploaded = client.post(
        f"/api/projects/{pid}/assets",
        json={"name": "badge.png", "image_data": data_url("red")},
    )
    aid = uploaded.json()["asset_id"]
    overlay = {"asset_id": aid, "x": 10, "y": 10, "width": 40, "height": 40}
    assert client.put(f"/api/projects/{pid}/scenes/scene_01/layout", json={"overlays": [overlay]}).status_code == 200
    assert client.delete(f"/api/projects/{pid}/assets/{aid}").status_code == 409
    assert client.put(f"/api/projects/{pid}/scenes/scene_01/layout", json={"overlays": []}).status_code == 200
    assert client.delete(f"/api/projects/{pid}/assets/{aid}").status_code == 200


def test_long_image_stale_after_layout_save_allows_view_but_blocks_download(project, client):
    pid, sb, folder = project
    lettering.letter_all(pid, sb)
    compose.make_long_image(pid, sb)
    assert client.get(f"/api/projects/{pid}").json()["long_image_stale"] is False
    changed = copy.deepcopy(store.load_storyboard(pid))
    # Headings are storyboard text and do not mark a scene panel render stale,
    # but they are part of the long-image output and must invalidate download.
    changed["scenes"][0]["heading"] = "改过的章节标题"
    assert client.put(f"/api/projects/{pid}/storyboard", json=changed).status_code == 200

    detail = client.get(f"/api/projects/{pid}")
    assert detail.status_code == 200 and detail.json()["long_image_stale"] is True
    # The old render remains useful for inspection, but a stale render cannot
    # be downloaded as if it were the current saved layout.
    assert client.get(f"/api/files/{pid}/output/%E9%95%BF%E5%9B%BE.png").status_code == 200
    download = client.get(f"/api/files/{pid}/output/%E9%95%BF%E5%9B%BE.png?download=true")
    assert download.status_code == 409


def test_subject_transform_and_layer_order_roundtrip(client, project):
    pid, sb, folder = project
    sb["background_mode"] = "transparent"
    scene = sb["scenes"][0]
    scene["background_mode"] = "transparent"
    store.save_storyboard(pid, sb)
    raw = store.active_raw_path(pid, "scene_01")
    im = Image.new("RGBA", (600, 400))
    from PIL import ImageDraw
    ImageDraw.Draw(im).rectangle((20,20,580,380), fill="red")
    im.save(raw)
    body = {"subject_layout":{"x":100,"y":100,"width":600,"height":400},
            "bubbles":[{"text":"测试文字", "x":100,"y":100,"width":420,"font_size":36,"type":"speech"}],
            "layer_order":["b01","subject","text:b01","caption"]}
    response=client.put(f"/api/projects/{pid}/scenes/scene_01/layout",json=body)
    assert response.status_code==200,response.text
    lettering.letter_scene(pid,store.load_storyboard(pid),scene,force=True)
    with Image.open(folder / "output/scene_01.png") as result:
        assert result.getpixel((400,150))[0] > 240 and result.getpixel((400,150))[1] < 10
        assert result.getpixel((900,300))[3] == 0
    body["layer_order"]=["subject","b01","text:b01","caption"]
    assert client.put(f"/api/projects/{pid}/scenes/scene_01/layout",json=body).status_code==200
    lettering.letter_scene(pid,store.load_storyboard(pid),scene,force=True)
    with Image.open(folder / "output/scene_01.png") as result:
        assert result.getpixel((400,150))[1] > 200
    assert store.load_scene_meta(pid,"scene_01")["subject_layout"]==body["subject_layout"]


def test_reference_identity_matches_attachment_order(project, monkeypatch):
    pid,sb,folder=project
    sb["characters"][0]["role"]="骗子"
    reference=folder / "characters/user_01.png"
    Image.new("RGB",(30,30),"green").save(reference)
    calls=[]
    def edit(prompt, refs, out, **kwargs):
        calls.append(prompt)
        Image.new("RGB",(600,400),"white").save(out)
    monkeypatch.setattr(image_gen,"edit",edit)
    scenes.generate_scene(pid,sb,sb["scenes"][0],{"user_01":reference},force=True,edit_instruction="保留身份")
    assert "Image 2 = user_01" in calls[0]
    assert "fixed story role: 骗子" in calls[0]


@pytest.mark.parametrize("kind", ["speech", "asset_cloud"])
def test_fixed_bubble_tail_and_sprite_flip(kind):
    from PIL import ImageChops
    font=lettering.load_font(30)
    b={"type":kind,"x":100,"y":100,"width":400,"body_height":300,"font_size":30,"text":""}
    g=bubbles.geometry(b,font)
    fixed={**b,"tail_local":g["tip"]}
    moved=bubbles.geometry({**fixed,"x":240,"y":150,"rotation":45},font)
    assert moved["tip"]==g["tip"]
    mirrored={**fixed,"flip_x":True,"flip_y":True}
    point=[40,60]
    assert bubbles.untransform_point(bubbles.transform_point(point,mirrored),mirrored)==pytest.approx(point)
    if kind=="asset_cloud":
        a=Image.new("RGBA",(600,500));bubbles.paint(a,fixed,font,include_text=False)
        z=Image.new("RGBA",(600,500));bubbles.paint(z,mirrored,font,include_text=False)
        expected=a.crop((100,100,500,400)).transpose(Image.Transpose.FLIP_LEFT_RIGHT).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        difference=ImageChops.difference(expected,z.crop((100,100,500,400)))
        assert difference.getbbox() is None


def test_bubble_variants_and_flip_saved(client,project):
    pid,sb,folder=project
    b={"text":"独立文字","type":"asset_cloud","bubble_variant":"transparent","flip_x":True,"flip_y":True,
       "x":100,"y":100,"width":400,"body_height":300,"font_size":30,"tail_local":[0,0]}
    response=client.put(f"/api/projects/{pid}/scenes/scene_01/layout",json={"bubbles":[b]})
    assert response.status_code==200,response.text
    saved=store.load_scene_meta(pid,"scene_01")["bubbles"][0]
    assert saved["flip_x"] and saved["flip_y"] and saved["bubble_variant"]=="transparent"
    image=Image.new("RGBA",(600,500));bubbles.paint(image,{**saved,"text":""},lettering.load_font(30),include_text=False)
    assert image.getpixel((300,250))[3]==0
    b["bubble_variant"]="missing"
    assert client.put(f"/api/projects/{pid}/scenes/scene_01/layout",json={"bubbles":[b]}).status_code==422


def test_add_delete_text_and_keep_group_identity(client, project):
    pid, sb, folder = project
    url = f"/api/projects/{pid}/scenes/scene_01/layout"
    def box(bid, text, x):
        return {"bubble_id":bid,"text":text,"type":"speech","x":x,"y":40,"width":300,"font_size":30}
    rows = [box("b01","第一条",30),box("b_new","新增文字",370),box("b_last","保留的位置",700)]
    rows[1]["bubble_visible"] = False
    payload = {"bubbles":rows,"element_groups":[["b_last","text:b_last"]]}
    assert client.put(url,json=payload).status_code == 200
    # Removing an earlier element must not transfer its layout to the last one.
    payload["bubbles"] = [rows[0],rows[2]]
    assert client.put(url,json=payload).status_code == 200
    current = store.load_storyboard(pid)
    lettering.letter_scene(pid,current,current["scenes"][0],force=True)
    saved = store.load_scene_meta(pid,"scene_01")
    assert [(b["bubble_id"],b["x"]) for b in saved["bubbles"]] == [("b01",30),("b_last",700)]
    assert saved["element_groups"] == [["b_last","text:b_last"]]
    payload["bubbles"][1]["text_visible"] = False
    payload.pop("element_groups")
    assert client.put(url,json=payload).status_code == 200
    assert store.load_scene_meta(pid,"scene_01")["element_groups"] == []
    assert client.put(url,json={"bubbles":[]}).status_code == 200
    current=store.load_storyboard(pid)
    lettering.letter_scene(pid,current,current["scenes"][0],force=True)
    assert store.load_scene_meta(pid,"scene_01")["bubbles"] == []
    assert current["scenes"][0]["dialogues"] == []


@pytest.mark.parametrize("mode",["scene","transparent"])
def test_text_only_and_bubble_only_render_independently(client,project,mode):
    pid,sb,folder=project
    sb["background_mode"]=mode
    store.save_storyboard(pid,sb)
    image=Image.new("RGBA",(600,400),(0,0,0,0) if mode=="transparent" else "#a8c7e8")
    if mode=="transparent":
        image.putpixel((599,399),(100,120,130,255))
    image.save(store.active_raw_path(pid,"scene_01"))
    b={"bubble_id":"b01","type":"speech","text":"测试文字","x":100,"y":100,"width":400,"body_height":150,"font_size":30,
       "bubble_visible":False,"text_visible":False}
    url=f"/api/projects/{pid}/scenes/scene_01/layout"
    assert client.put(url,json={"bubbles":[b]}).status_code==200
    current=store.load_storyboard(pid)
    lettering.letter_scene(pid,current,current["scenes"][0],force=True)
    with Image.open(folder/"output/scene_01_panel.png") as result:
        assert result.getpixel((150,150)) == ((0,0,0,0) if mode=="transparent" else (168,199,232,255))
    b["bubble_visible"]=True
    assert client.put(url,json={"bubbles":[b]}).status_code==200
    lettering.letter_scene(pid,current,current["scenes"][0],force=True)
    with Image.open(folder/"output/scene_01_panel.png") as result:
        assert result.getpixel((150,150)) == (255,255,255,255)


def test_footer_text_and_image_preview_save_and_asset_usage(client,project):
    pid,sb,folder=project
    lettering.letter_all(pid,sb)
    record=assets.create_asset(pid,data_url("red"),kind="image")
    plain,_=compose.render_long_image(pid,sb)
    blocks=[{"id":"t1","type":"text","text":"请通过官方渠道核实","font_size":40,"align":"left"},
            {"id":"i1","type":"image","asset_id":record["asset_id"],"width":400,"align":"right"}]
    sb["long_layout"]={"footer_blocks":blocks}
    response=client.put(f"/api/projects/{pid}/storyboard",json=sb)
    assert response.status_code==200,response.text
    result,layout=compose.render_long_image(pid,store.load_storyboard(pid))
    assert result.height>plain.height+600
    image_y=layout["footer_blocks"][1]["y"]
    assert result.getpixel((900,image_y+100)) == (255,0,0)
    assert image_y+layout["footer_blocks"][1]["height"]<result.height
    assert client.post(f"/api/projects/{pid}/long-preview",json=sb["long_layout"]).status_code==200
    assert client.delete(f"/api/projects/{pid}/assets/{record['asset_id']}").status_code==409
    blocks[1]["asset_id"]="missing_asset"
    assert client.post(f"/api/projects/{pid}/long-preview",json={"footer_blocks":blocks}).status_code==422


@pytest.mark.parametrize("template", ["cards", "filmstrip", "comic_strip", "scroll"])
def test_page_margins_surround_content_and_export_centimeters(client, project, template):
    from PIL import ImageChops
    pid, sb, folder = project
    lettering.letter_all(pid, sb)
    record = assets.create_asset(pid, data_url("red"), kind="image")
    options = {"template_id":template, "footer":"结尾提示", "footer_blocks":[
        {"type":"text","text":"核实以后再决定。"},
        {"type":"image","asset_id":record["asset_id"],"width":200},
    ]}
    base, before = compose.render_long_image(pid, sb, options)
    options.update({"margin_top_cm":1.5,"margin_bottom_cm":2.5,"print_width_cm":20})
    padded, after = compose.render_long_image(pid, sb, options)
    assert padded.size == (1080, base.height+81+135)
    assert ImageChops.difference(base, padded.crop((0,81,1080,81+base.height))).getbbox() is None
    bg = TEMPLATES[template]["background"]
    if template == "scroll":
        accent = Image.new("RGB", (1, 1), TEMPLATES[template]["accent"]).getpixel((0, 0))
        background = Image.new("RGB", (1, 1), bg).getpixel((0, 0))
        # The page border remains continuous across both margin/content joins.
        for y in (0, 40, 80, 81, 101, padded.height - 136, padded.height - 135, padded.height - 1):
            for x in (25, 36, 1044, 1055):
                assert padded.getpixel((x, y)) == accent
            assert padded.getpixel((30, y)) == background
        assert padded.getpixel((540, 40)) == background
    else:
        assert ImageChops.difference(padded.crop((0,0,1080,81)),Image.new("RGB",(1080,81),bg)).getbbox() is None
        assert ImageChops.difference(padded.crop((0,padded.height-135,1080,padded.height)),Image.new("RGB",(1080,135),bg)).getbbox() is None
    assert after["scenes"][0]["y"] == before["scenes"][0]["y"]+81
    assert after["footer_blocks"][-1]["y"] == before["footer_blocks"][-1]["y"]+81
    sb["long_layout"] = options
    response = client.put(f"/api/projects/{pid}/storyboard", json=sb)
    assert response.status_code == 200, response.text
    assert store.load_storyboard(pid)["long_layout"]["margin_bottom_cm"] == 2.5
    exported = compose.make_long_image(pid, store.load_storyboard(pid))
    with Image.open(exported) as image:
        assert image.size == padded.size
        assert abs(image.width / image.info["dpi"][0] * 2.54 - 20) < .001
    assert client.post(f"/api/projects/{pid}/long-preview",json=options).status_code == 200
    narrower, dimensions = compose.render_long_image(pid, sb, {**options,"print_width_cm":10})
    assert dimensions["page_margins"]["top_px"] == 162
    assert narrower.height == base.height+162+270


def test_page_margins_reject_invalid_units_and_sizes(client, project):
    pid, _, _ = project
    for patch in [{"margin_top_cm":-1},{"margin_bottom_cm":21},{"margin_top_cm":"2"},
                  {"margin_bottom_cm":True},{"print_width_cm":0},{"print_width_cm":101}]:
        assert client.post(f"/api/projects/{pid}/long-preview",json=patch).status_code == 422


@pytest.mark.parametrize("template", ["cards", "gallery_grid"])
@pytest.mark.parametrize("opacity", [0, .5, 1])
def test_page_background_color_alpha_and_saved_png(client, project, template, opacity):
    pid, sb, _ = project
    lettering.letter_all(pid, sb)
    record = assets.create_asset(pid, data_url("red"), kind="image")
    options = {"template_id": template, "background_color": "#123456", "background_opacity": opacity,
               "margin_top_cm": 1, "margin_bottom_cm": 1,
               "footer_blocks": [{"type": "image", "asset_id": record["asset_id"], "width": 200}]}
    sb["long_layout"] = options
    assert client.put(f"/api/projects/{pid}/storyboard", json=sb).status_code == 200
    saved = store.load_storyboard(pid)
    assert saved["long_layout"]["background_opacity"] == opacity
    image, layout = compose.render_long_image(pid, saved)
    expected = (18, 52, 86, round(opacity * 255))
    assert image.convert("RGBA").getpixel((0, 0)) == expected
    assert image.convert("RGBA").getpixel((0, image.height - 1)) == expected
    # Making the page transparent must not fade the inserted illustration.
    assert image.convert("RGBA").getpixel((540, layout["footer_blocks"][0]["y"] + 30)) == (255, 0, 0, 255)
    with Image.open(compose.make_long_image(pid, saved)) as exported:
        assert exported.convert("RGBA").getpixel((0, 0)) == expected
    response = client.post(f"/api/projects/{pid}/long-preview", json=options)
    assert response.status_code == 200
    with Image.open(io.BytesIO(response.content)) as preview:
        pixel = preview.convert("RGBA").getpixel((0, 0))
        assert pixel[3] == expected[3]
        # Preview resampling uses premultiplied alpha, with one-level rounding.
        if opacity:
            assert all(abs(actual - wanted) <= 1 for actual, wanted in zip(pixel[:3], expected[:3]))


def test_footer_spacing_moves_image_and_following_content_without_fading_alpha(client, project):
    pid, sb, _ = project
    lettering.letter_all(pid, sb)
    encoded = io.BytesIO()
    Image.new("RGBA", (200, 200), (240, 80, 20, 128)).save(encoded, format="PNG")
    record = assets.create_asset(pid, "data:image/png;base64," + base64.b64encode(encoded.getvalue()).decode(), kind="image")
    blocks = [{"type": "text", "text": "前文"},
              {"type": "image", "asset_id": record["asset_id"], "width": 200, "gap_before_cm": 0},
              {"type": "text", "text": "后文"}]
    options = {"background_opacity": 0, "print_width_cm": 20, "footer_blocks": blocks}
    before_image, before = compose.render_long_image(pid, sb, options)
    blocks[1]["gap_before_cm"] = 2.5
    after_image, after = compose.render_long_image(pid, sb, options)
    assert after["scenes"] == before["scenes"]
    assert after["footer_blocks"][0]["y"] == before["footer_blocks"][0]["y"]
    for index in (1, 2):
        assert after["footer_blocks"][index]["y"] == before["footer_blocks"][index]["y"] + 135
    assert after_image.height == before_image.height + 135
    assert after_image.getpixel((540, after["footer_blocks"][1]["y"] + 50)) == (240, 80, 20, 128)
    sb["long_layout"] = options
    assert client.put(f"/api/projects/{pid}/storyboard", json=sb).status_code == 200
    assert store.load_storyboard(pid)["long_layout"]["footer_blocks"][1]["gap_before_cm"] == 2.5


def test_page_background_and_footer_gap_reject_invalid_values(client, project):
    pid, _, _ = project
    for patch in [{"background_color": "red"}, {"background_color": True},
                  {"background_opacity": -1}, {"background_opacity": 2}, {"background_opacity": "0.5"}, {"background_opacity": True},
                  *[{"footer_blocks": [{"type": "text", "text": "提示", "gap_before_cm": gap}]} for gap in (-1, 21, True, "2")]]:
        assert client.post(f"/api/projects/{pid}/long-preview", json=patch).status_code == 422


def test_generated_footer_asset_two_references_and_failure_retry(client,project,monkeypatch):
    pid,sb,folder=project
    refs=[assets.create_asset(pid,data_url(color),kind="image") for color in ["red","blue"]]
    calls=[]
    def edit(prompt,ref_paths,path,**kwargs):
        calls.append((prompt,ref_paths,kwargs))
        Image.new("RGBA",(160,120),"green").save(path)
    monkeypatch.setattr(image_gen,"edit",edit)
    def submit(kind,pid,detail,fn):
        import uuid
        task=tasks.Task(task_id=uuid.uuid4().hex,kind=kind,project_id=pid,detail=detail)
        tasks._tasks[task.task_id]=task
        tasks._run(task,fn)
        return task
    monkeypatch.setattr(tasks,"submit",submit)
    body={"prompt":"让图1人物拿着图2的卡片","reference_asset_ids":[r["asset_id"] for r in refs]}
    url=f"/api/projects/{pid}/assets/generate"
    response=client.post(url,json=body)
    assert response.status_code==202,response.text
    t=client.get(f"/api/tasks/{response.json()['task_id']}").json()
    assert t["status"]=="done" and t["result"]["asset"]["width"]==160
    assert calls[0][1]==[assets.asset_path(pid,r["asset_id"]) for r in refs]
    assert calls[0][2]["allow_reference_fallback"] is False
    assert calls[0][2]["request_timeout"]==240
    assert client.post(url,json={**body,"reference_asset_ids":body["reference_asset_ids"]+["missing"]}).status_code==422
    def fail(*args,**kwargs): raise RuntimeError("图片服务暂时不可用")
    monkeypatch.setattr(image_gen,"edit",fail)
    failed=client.post(url,json=body)
    t=client.get(f"/api/tasks/{failed.json()['task_id']}").json()
    assert t["status"]=="failed" and "图片服务暂时不可用" in t["error"]
    assert t["result"] is None
    monkeypatch.setattr(image_gen,"edit",edit)
    retry=client.post(url,json=body)
    assert client.get(f"/api/tasks/{retry.json()['task_id']}").json()["status"]=="done"
