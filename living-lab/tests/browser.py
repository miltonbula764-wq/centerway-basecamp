"""Private panel smoke against local synthetic state. Playwright is test-only."""

import json
import os
import tempfile
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from lab.engine import tick
from lab.imports import comparisons
from lab.store import initialize, connect
from lab.web import make_server


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = json.loads(
            (Path(__file__).parents[1] / "config.example.json").read_text()
        )
        cfg.update(
            state_dir=str(root / "state"), admin_password_file=str(root / "admin")
        )
        password = "controlled-browser-password-only-207b"
        (root / "admin").write_text(password)
        paths = {c["id"]: initialize(cfg, c) for c in cfg["companies"]}
        now = time.time()
        for c in cfg["companies"]:
            db = connect(paths[c["id"]])
            for n in range(6):
                tick(db, cfg, c, now - 300 + n * 60, historical=True)
            comparisons(
                db,
                c,
                {
                    "company": c["id"],
                    "evaluations": [
                        {
                            "external_id": "controlled-browser-fixture",
                            "client": c["id"] + "-001",
                            "indicator": "cycle_minutes",
                            "observed_until": now,
                            "actual_result": "inconclusive <script>window.pwned=1</script>",
                            "evidence_ref": "controlled fixture; not a CENTERWAY evaluation",
                        }
                    ],
                },
                now,
            )
            db.close()
        server = make_server(cfg, paths, {}, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = "http://127.0.0.1:" + str(server.server_port)
        errors = []
        artifacts = Path("artifacts")
        artifacts.mkdir(exist_ok=True)
        try:
            with sync_playwright() as p:
                options = {"headless": True}
                if os.environ.get("LAB_BROWSER_BIN"):
                    options["executable_path"] = os.environ["LAB_BROWSER_BIN"]
                browser = p.chromium.launch(**options)
                anon = browser.new_context()
                r = anon.request.get(url + "/api/state")
                assert r.status == 401
                anon.close()
                for viewport, label in [
                    ({"width": 1280, "height": 960}, "desktop"),
                    ({"width": 390, "height": 844}, "mobile"),
                ]:
                    context = browser.new_context(
                        viewport=viewport,
                        http_credentials={
                            "username": cfg["admin_user"],
                            "password": password,
                        },
                    )
                    context.route(
                        "**/*",
                        lambda route: route.continue_()
                        if route.request.url.startswith(url + "/")
                        else route.abort(),
                    )
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(url)
                    expect(
                        page.get_by_role("heading", name="Operações em movimento")
                    ).to_be_visible()
                    expect(page.locator("section")).to_have_count(2)
                    atlas = page.locator("section").filter(
                        has=page.get_by_role("heading", name="Atlas Support SaaS")
                    )
                    beacon = page.locator("section").filter(
                        has=page.get_by_role("heading", name="Beacon Workflow SaaS")
                    )
                    atlas.get_by_role("button", name="Pausar", exact=True).click()
                    expect(atlas.get_by_text("Pausada", exact=True)).to_be_visible()
                    expect(
                        beacon.get_by_text("Em execução", exact=True)
                    ).to_be_visible()
                    page.reload()
                    expect(atlas.get_by_text("Pausada", exact=True)).to_be_visible()
                    atlas.get_by_role("button", name="Retomar", exact=True).click()
                    expect(atlas.get_by_text("Em execução", exact=True)).to_be_visible()
                    atlas.get_by_text(
                        "Avaliações CENTERWAY importadas", exact=False
                    ).click()
                    expect(atlas.locator("details[open]")).to_have_count(1)
                    assert page.evaluate("window.pwned") is None
                    assert (
                        "private_events" in atlas.locator("details[open]").inner_text()
                    )
                    page.wait_for_timeout(5200)
                    expect(atlas.locator("details[open]")).to_have_count(1)
                    atlas.get_by_text(
                        "Verdade operacional privada", exact=False
                    ).click()
                    atlas.get_by_role(
                        "button", name="Próxima página de acontecimentos"
                    ).click()
                    expect(
                        atlas.get_by_text("Verdade operacional privada", exact=False)
                    ).to_contain_text("100–")
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"
                    )
                    page.screenshot(
                        path=str(artifacts / ("panel-" + label + ".png")),
                        full_page=True,
                    )
                    context.close()
                browser.close()
                assert not errors, errors
            print(
                "Browser passed: desktop/mobile; private auth; independent pause/reload/resume; pagination; details persist; inert imported text; no page errors"
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    main()
