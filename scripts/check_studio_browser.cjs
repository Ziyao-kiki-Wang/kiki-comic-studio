const {
  chromium,
} = require("C:/Users/10633/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
const fs = require("fs"),
  path = require("path"),
  assert = require("assert/strict");
const out = path.resolve("output/studio-validation");
(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const errors = [],
    failed = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("response", (r) => {
    if (r.status() >= 500) failed.push(r.url() + ":" + r.status());
  });
  try {
    await page.goto("http://127.0.0.1:5174/");
    await page.getByRole("heading", { name: "AI 漫画长图生产工具" }).waitFor();
    fs.writeFileSync(
      path.join(out, "creation-snapshot.txt"),
      await page.locator("body").ariaSnapshot(),
    );
    await page
      .locator("input[type=file]")
      .setInputFiles(
        path.resolve("projects/comic_20260907_092215/characters/C01.png"),
      );
    await page.getByAltText("角色 1 参考图").waitFor();
    assert.equal(
      await page.getByLabel("角色名称", { exact: true }).inputValue(),
      "角色1",
    );
    await page.getByLabel("角色名称", { exact: true }).fill("固定主人公");
    await page.getByLabel(/场景背景/).selectOption("transparent");
    await page.screenshot({
      path: path.join(out, "creation.png"),
      fullPage: true,
    });
    await page.goto("http://127.0.0.1:5174/project/studio_preview");
    await page.getByRole("heading", { name: "分镜工作室" }).waitFor();
    const assetDownload = page.waitForEvent("download");
    await page
      .getByRole("link", { name: "下载原图", exact: true })
      .first()
      .click();
    assert((await assetDownload).suggestedFilename().endsWith(".png"));
    await page.getByRole('link', {name:'长图排版 03'}).click();
    await page.getByRole('heading', {name:'长图出版编辑器'}).waitFor();
    assert.equal(await page.locator('.publishing-template').count(), 11);
    await page.locator('.publishing-template-preview img').first().waitFor({timeout:60000});
    await page
      .locator(".publishing-template")
      .filter({ hasText: "事件时间轴" })
      .click();
    await page.getByAltText("事件时间轴长图预览").waitFor();
    await page.getByLabel(/统一格间距/).evaluate((el) => {
      Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      ).set.call(el, "120");
      el.dispatchEvent(new Event("input", { bubbles: true }));
    });
    for (const [label, value] of [[/标题顶部留白/, '96'], [/文字字间距/, '4']]) {
      await page.getByLabel(label).evaluate((el, v) => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,v);
        el.dispatchEvent(new Event('input',{bubbles:true}));
      }, value);
    }
    await page.getByText("单独调整两格之间的距离", { exact: true }).click();
    await page.getByLabel("第 1 格与第 2 格", { exact: true }).fill("200");
    await page.getByRole("button", { name: "保存排版并生成长图" }).click();
    await page
      .getByText("任务完成", { exact: true })
      .waitFor({ timeout: 60000 });
    const options = await page.evaluate(async () => {
      const p = await fetch(
        "http://127.0.0.1:8001/api/projects/studio_preview",
      );
      return (await p.json()).storyboard.long_layout;
    });
    assert.equal(options.title_top, 96);
    assert.equal(options.letter_spacing, 4);
    assert.equal(options.template_id, "timeline");
    assert.equal(options.gap, 120);
    assert.equal(options.gaps.scene_01, 200);
    await page.waitForFunction(
      () => document.querySelectorAll(".publishing-template-preview img").length === 11,
      { timeout: 60000 },
    );
    await page
      .locator(".publishing-template-list")
      .screenshot({ path: path.join(out, "template-options.png") });
    await page.screenshot({
      path: path.join(out, "workbench.png"),
      fullPage: true,
    });
    await page.goto(
      "http://127.0.0.1:5174/project/studio_preview/scene/scene_01/edit",
    );
    await page.getByRole("heading", { name: "气泡库", exact: true }).waitFor();
    await page.getByLabel(/当前对话/).selectOption("b01");
    await page.getByRole("button", { name: "震惊爆炸", exact: true }).click();
    assert.equal(
      await page.evaluate(() => window.__editorStage.find(".tail-tip").length),
      0,
    );
    fs.writeFileSync(
      path.join(out, "editor-snapshot.txt"),
      await page.locator("body").ariaSnapshot(),
    );
    await page
      .getByRole("textbox", { name: "台词", exact: true })
      .fill("真的？\n先核实再决定！");
    await page.getByRole("button", { name: "日常圆角", exact: true }).click();
    await page.getByLabel(/尾巴出口/).selectOption("left");
    await page.getByLabel("尖端 X", { exact: true }).fill("240");
    await page.getByLabel("尖端 Y", { exact: true }).fill("450");
    assert.equal(
      await page.evaluate(() => window.__editorStage.find(".tail-tip").length),
      1,
    );
    const tip = await page.evaluate(() => {
      const n = window.__editorStage.findOne(".tail-tip");
      const p = n.getAbsolutePosition();
      const r = window.__editorStage.container().getBoundingClientRect();
      return { x: p.x + r.x, y: p.y + r.y };
    });
    await page.mouse.move(tip.x, tip.y);
    await page.mouse.down();
    await page.mouse.move(tip.x + 40, tip.y + 15, { steps: 10 });
    await page.mouse.up();
    assert(
      Number(await page.getByLabel("尖端 X", { exact: true }).inputValue()) >
        240,
      "Tip drag changes endpoint",
    );
    await page.getByRole("button", { name: "震惊爆炸", exact: true }).click();
    await page.getByRole("button", { name: "浅紫无边框", exact: true }).click();
    await page.getByRole("button", { name: "保存并更新长图" }).click();
    await page
      .getByText("已保存，单格与长图均已更新", { exact: true })
      .waitFor({ timeout: 60000 });
    await page.reload();
    await page.getByLabel(/当前对话/).selectOption("b01");
    assert.equal(
      await page
        .getByRole("textbox", { name: "台词", exact: true })
        .inputValue(),
      "真的？\n先核实再决定！",
    );
    assert.equal(await page.getByLabel(/边框粗细/).inputValue(), "0");
    assert.equal(
      await page.getByLabel("底色", { exact: true }).inputValue(),
      "#eeebf7",
    );
    assert.equal(
      await page.evaluate(() => window.__editorStage.find(".tail-tip").length),
      0,
      "Burst stays tailless after save/reload",
    );
    await page.screenshot({
      path: path.join(out, "editor.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: path.join(out, "editor-mobile.png"),
      fullPage: true,
    });
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 2,
      ),
      "Mobile editor does not overflow",
    );
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("http://127.0.0.1:5174/project/studio_preview");
    const download = page.waitForEvent("download", { timeout: 60000 });
    await page.getByRole("button", { name: "导出 PPTX", exact: true }).click();
    const file = await download;
    await file.saveAs(path.join(out, "comic-editable.pptx"));
    assert(fs.statSync(path.join(out, "comic-editable.pptx")).size > 100000);
    let editRequest;
    await page.route(
      "**/api/projects/studio_preview/generate",
      async (route) => {
        editRequest = route.request().postDataJSON();
        await route.fulfill({
          status: 202,
          contentType: "application/json",
          body: JSON.stringify({ task_id: "mock-edit" }),
        });
      },
    );
    await page.route("**/api/tasks/mock-edit", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "done", logs: [] }),
      }),
    );
    await page
      .getByLabel("图片修改要求", { exact: true })
      .first()
      .fill("保留桌椅，让手机自然展示");
    await page
      .getByRole("button", { name: "按要求修改图片", exact: true })
      .first()
      .click();
    await page.waitForResponse((r) => r.url().endsWith("/api/tasks/mock-edit"));
    assert.equal(editRequest.action, "edit_scene");
    assert.equal(editRequest.instruction, "保留桌椅，让手机自然展示");
    assert.equal(errors.length, 0, errors.join("\n"));
    assert.equal(failed.length, 0, failed.join("\n"));
    console.log(
      JSON.stringify({
        upload: "passed",
        templates: 11,
        spacing: "persisted",
        tailDrag: "passed",
        burst: "persisted",
        mobile: "passed",
        pptx: "downloaded",
        errors,
        failed,
      }),
    );
  } catch (e) {
    await page.screenshot({
      path: path.join(out, "browser-failure.png"),
      fullPage: true,
    });
    fs.writeFileSync(
      path.join(out, "failure-snapshot.txt"),
      await page.locator("body").ariaSnapshot(),
    );
    console.error("Browser errors:", errors);
    throw e;
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
