"""Deterministic static verification for generated web artifacts."""

from __future__ import annotations

import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .artifact_profile import ArtifactProfile, ArtifactProfileDetector, _candidate_files


BrowserRunner = Callable[[dict[str, object]], dict[str, object]]


PROTECTED_TERMS = (
    "mario",
    "nintendo",
    "luigi",
    "peach",
    "bowser",
    "toad",
    "goomba",
    "koopa",
    "mushroom kingdom",
    "超级玛丽",
)


@dataclass(slots=True)
class ArtifactVerification:
    status: str
    summary: str
    evidence: list[str] = field(default_factory=list)
    tests_passed: list[str] = field(default_factory=list)
    tests_failed: list[str] = field(default_factory=list)
    profile: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "summary": self.summary,
            "evidence": list(self.evidence),
            "tests_passed": list(self.tests_passed),
            "tests_failed": list(self.tests_failed),
            "profile": dict(self.profile),
        }


@dataclass(slots=True)
class BrowserArtifactEvidence:
    status: str
    summary: str
    url: str = ""
    screenshots: dict[str, str] = field(default_factory=dict)
    pixel_diff: dict[str, object] = field(default_factory=dict)
    semantic_probe: dict[str, object] = field(default_factory=dict)
    scenario_probe: dict[str, object] = field(default_factory=dict)
    gameplay_probe: dict[str, object] = field(default_factory=dict)
    console_errors: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    tests_passed: list[str] = field(default_factory=list)
    tests_failed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "summary": self.summary,
            "url": self.url,
            "screenshots": dict(self.screenshots),
            "pixel_diff": dict(self.pixel_diff),
            "semantic_probe": dict(self.semantic_probe),
            "scenario_probe": dict(self.scenario_probe),
            "gameplay_probe": dict(self.gameplay_probe),
            "console_errors": list(self.console_errors),
            "evidence": list(self.evidence),
            "tests_passed": list(self.tests_passed),
            "tests_failed": list(self.tests_failed),
        }


class StaticWebArtifactVerifier:
    """Verify static HTML/canvas artifacts without launching a browser."""

    def __init__(self, profile_detector: ArtifactProfileDetector | None = None) -> None:
        self.profile_detector = profile_detector or ArtifactProfileDetector()

    def verify(
        self,
        repository_path: str | Path,
        files: list[str],
        *,
        objective: str = "",
        requirements: list[str] | None = None,
    ) -> ArtifactVerification:
        repo = Path(repository_path).resolve()
        selected_files = _candidate_files(repo, dedupe(files or ["index.html"]))
        profile = self.profile_detector.detect(repo, selected_files, objective=objective, requirements=requirements)
        if profile.name not in {"canvas_game", "static_web_app"}:
            return ArtifactVerification(
                status="skipped",
                summary=f"Static web artifact inspection skipped for {profile.name} profile.",
                evidence=[f"Artifact profile {profile.name} is not a static web artifact."],
                tests_passed=["static artifact inspection skipped"],
                tests_failed=[],
                profile=profile.to_dict(),
            )
        evidence: list[str] = []
        failures: list[str] = []
        texts: dict[str, str] = {}

        for file_path in selected_files:
            target = (repo / file_path).resolve()
            try:
                target.relative_to(repo)
            except ValueError:
                failures.append(f"Artifact path is outside repository: {file_path}")
                continue
            if not target.exists():
                failures.append(f"Missing artifact file: {file_path}")
                continue
            if target.is_dir():
                continue
            text = target.read_text(encoding="utf-8", errors="replace")
            texts[file_path] = text
            evidence.append(f"Found artifact file: {file_path}")

        html = "\n".join(text for path, text in texts.items() if path.endswith(".html"))
        combined = "\n".join(texts.values())
        lowered = combined.lower()

        if any(path.endswith(".html") for path in selected_files):
            if not html:
                failures.append("No HTML entrypoint content was available.")
            elif profile.name == "canvas_game" and "<canvas" not in html.lower() and "game" not in html.lower():
                failures.append("HTML entrypoint does not expose a canvas or game root.")
            elif profile.name == "static_web_app" and not static_web_root_present(html):
                failures.append("HTML entrypoint does not expose a static web app root.")
            else:
                evidence.append("HTML entrypoint exposes an app root.")

        if profile.name == "canvas_game":
            if "requestanimationframe" in lowered or re.search(r"\bsetinterval\s*\(", lowered):
                evidence.append("Animation or render loop is present.")
            else:
                failures.append("No animation or render loop was detected.")
        elif profile.name == "static_web_app":
            if static_web_controls_present(combined):
                evidence.append("Static web app interactive controls are present.")
            else:
                evidence.append("Static web app has no detected interactive controls.")
        else:
            if "requestanimationframe" in lowered or re.search(r"\bsetinterval\s*\(", lowered):
                evidence.append("Animation or render loop is present.")

        if profile.name == "canvas_game":
            control_markers = ("keydown", "keyup", "arrowleft", "arrowright", "space", "keya", "keyd", "pointerdown", "touch")
            if any(marker in lowered for marker in control_markers):
                evidence.append("Keyboard or touch controls are present.")
            else:
                failures.append("No keyboard or touch controls were detected.")

            gameplay_markers = ("tile", "level", "player", "enemy", "coin", "flag", "score", "timer", "collision", "physics")
            found_gameplay = [marker for marker in gameplay_markers if marker in lowered]
            if len(found_gameplay) >= 5:
                evidence.append("Gameplay markers present: " + ", ".join(found_gameplay[:8]))
            else:
                failures.append("Insufficient gameplay markers for platformer artifact.")

        if profile.name == "canvas_game":
            if "__ALCHEMY_GAME_TEST__" not in combined:
                failures.append("Canvas game does not expose window.__ALCHEMY_GAME_TEST__ gameplay probe hook.")
            else:
                evidence.append("Canvas game exposes window.__ALCHEMY_GAME_TEST__ gameplay probe hook.")
            for hook_name in ("snapshot", "advanceToVictory", "restart"):
                if hook_name not in combined:
                    failures.append(f"Canvas game gameplay probe is missing {hook_name}().")
                else:
                    evidence.append(f"Canvas game gameplay probe includes {hook_name}().")

        if profile.name == "canvas_game":
            protected = [term for term in PROTECTED_TERMS if term in lowered]
            if protected:
                failures.append("Protected terms found in generated artifact: " + ", ".join(protected))
            else:
                evidence.append("No protected commercial game terms were found in generated artifact files.")

        status = "failed" if failures else "completed"
        return ArtifactVerification(
            status=status,
            summary="Static web artifact inspection passed." if status == "completed" else "Static web artifact inspection failed.",
            evidence=evidence,
            tests_passed=["static artifact inspection"] if status == "completed" else [],
            tests_failed=failures,
            profile=profile.to_dict(),
        )


class BrowserArtifactEvidenceVerifier:
    """Validate persisted browser evidence such as screenshots and pixel diff."""

    def verify_existing_evidence(
        self,
        *,
        output_dir: str | Path,
        url: str = "",
        initial_screenshot: str | Path = "",
        after_interaction_screenshot: str | Path = "",
        console_errors: list[str] | None = None,
        require_pixel_change: bool = True,
        require_nonblank: bool = False,
    ) -> BrowserArtifactEvidence:
        output = Path(output_dir)
        screenshots: dict[str, str] = {}
        failures: list[str] = []
        evidence: list[str] = []
        errors = list(console_errors or [])

        initial = _resolve_evidence_path(output, initial_screenshot)
        after = _resolve_evidence_path(output, after_interaction_screenshot)
        if initial:
            screenshots["initial"] = str(initial)
            evidence.append(f"Initial browser screenshot recorded: {initial}")
        else:
            failures.append("Initial browser screenshot is missing.")
        if after:
            screenshots["after_interaction"] = str(after)
            evidence.append(f"Post-interaction browser screenshot recorded: {after}")
        else:
            failures.append("Post-interaction browser screenshot is missing.")

        pixel_diff: dict[str, object] = {}
        if initial and after:
            pixel_diff = compute_image_diff(initial, after)
            if pixel_diff.get("error"):
                failures.append(str(pixel_diff["error"]))
            changed = int(pixel_diff.get("changed_pixels", 0))
            if changed > 0:
                evidence.append(f"Browser interaction changed {changed} screenshot pixels.")
            elif require_pixel_change:
                failures.append("Browser screenshots did not change after interaction.")

        if require_nonblank and initial and image_is_uniform(initial):
            failures.append("Initial browser screenshot appears blank or uniform.")
        elif require_nonblank and initial:
            evidence.append("Initial browser screenshot is non-uniform.")

        if errors:
            failures.append("Browser console errors were recorded: " + "; ".join(errors))
        else:
            evidence.append("No browser console errors were recorded.")

        status = "failed" if failures else "completed"
        return BrowserArtifactEvidence(
            status=status,
            summary="Browser artifact evidence passed." if status == "completed" else "Browser artifact evidence failed.",
            url=url,
            screenshots=screenshots,
            pixel_diff=pixel_diff,
            console_errors=errors,
            evidence=evidence,
            tests_passed=["browser artifact evidence"] if status == "completed" else [],
            tests_failed=failures,
        )


class BrowserArtifactRunner:
    """Run browser smoke verification for static repository artifacts."""

    def __init__(self, browser_runner: BrowserRunner | None = None) -> None:
        self.browser_runner = browser_runner or playwright_browser_runner

    def verify(
        self,
        repository_path: str | Path,
        files: list[str],
        *,
        output_dir: str | Path,
        profile_name: str = "unknown",
        timeout_seconds: float = 15,
        acceptance_scenarios: list[dict[str, object]] | None = None,
    ) -> BrowserArtifactEvidence:
        repo = Path(repository_path).resolve()
        selected = dedupe(files or ["index.html"])
        entrypoint = next((file for file in selected if file.endswith(".html")), "index.html")
        entrypoint_path = (repo / entrypoint).resolve()
        try:
            entrypoint_path.relative_to(repo)
        except ValueError:
            return BrowserArtifactEvidence(
                status="failed",
                summary="Browser artifact evidence failed.",
                tests_failed=[f"Browser entrypoint is outside repository: {entrypoint}"],
            )
        if not entrypoint_path.exists() or not entrypoint_path.is_file():
            return BrowserArtifactEvidence(
                status="failed",
                summary="Browser artifact evidence failed.",
                tests_failed=[f"Browser entrypoint is missing: {entrypoint}"],
            )

        output = Path(output_dir).resolve()
        output.mkdir(parents=True, exist_ok=True)
        initial = output / "browser_initial.png"
        after = output / "browser_after_interaction.png"

        server = _start_static_server(repo)
        entrypoint_url = entrypoint.replace("\\", "/")
        url = f"http://127.0.0.1:{server.server_address[1]}/{entrypoint_url}"
        runner_result: dict[str, object] = {}
        try:
            runner_result = self.browser_runner(
                {
                    "url": url,
                    "initial_screenshot": str(initial),
                    "after_interaction_screenshot": str(after),
                    "profile_name": profile_name,
                    "timeout_seconds": timeout_seconds,
                    "acceptance_scenarios": list(acceptance_scenarios or []),
                }
            )
        except Exception as exc:  # pragma: no cover - defensive around external browsers
            runner_result = {
                "status": "failed",
                "summary": f"Browser runner failed: {exc}",
                "tests_failed": [str(exc)],
            }
        finally:
            server.shutdown()
            server.server_close()

        browser = BrowserArtifactEvidenceVerifier().verify_existing_evidence(
            output_dir=output,
            url=url,
            initial_screenshot=initial,
            after_interaction_screenshot=after,
            console_errors=_string_list(runner_result.get("console_errors")),
            require_pixel_change=profile_name == "canvas_game",
            require_nonblank=profile_name in {"canvas_game", "static_web_app"},
        )
        gameplay_probe = runner_result.get("gameplay_probe")
        semantic_probe = runner_result.get("semantic_probe")
        scenario_probe = runner_result.get("scenario_probe")
        if isinstance(gameplay_probe, dict) and gameplay_probe:
            browser.gameplay_probe = dict(gameplay_probe)
            browser.semantic_probe = dict(gameplay_probe)
            gameplay_status = str(gameplay_probe.get("status", ""))
            if gameplay_status:
                browser.evidence.append(f"Gameplay probe: {gameplay_status}.")
            if gameplay_status == "failed" and not _string_list(gameplay_probe.get("tests_failed")):
                browser.tests_failed.append("Gameplay probe failed.")
            if profile_name == "canvas_game" and gameplay_status != "completed":
                browser.tests_failed.append(f"Canvas gameplay probe status is {gameplay_status or 'missing'}.")
            for passed in _string_list(gameplay_probe.get("tests_passed")):
                browser.tests_passed.append(passed)
            for failed in _string_list(gameplay_probe.get("tests_failed")):
                browser.tests_failed.append(failed)
        elif profile_name == "canvas_game":
            browser.tests_failed.append("Canvas game browser run did not return gameplay probe evidence.")
        if isinstance(semantic_probe, dict) and semantic_probe:
            browser.semantic_probe = dict(semantic_probe)
            semantic_status = str(semantic_probe.get("status", ""))
            if semantic_status:
                browser.evidence.append(f"Semantic probe: {semantic_status}.")
            if semantic_status == "failed" and not _string_list(semantic_probe.get("tests_failed")):
                browser.tests_failed.append("Semantic probe failed.")
            for passed in _string_list(semantic_probe.get("tests_passed")):
                browser.tests_passed.append(passed)
            for failed in _string_list(semantic_probe.get("tests_failed")):
                browser.tests_failed.append(failed)
        if isinstance(scenario_probe, dict) and scenario_probe:
            browser.scenario_probe = dict(scenario_probe)
            scenario_status = str(scenario_probe.get("status", ""))
            if scenario_status:
                browser.evidence.append(f"Scenario probe: {scenario_status}.")
            if scenario_status == "failed" and not _string_list(scenario_probe.get("tests_failed")):
                browser.tests_failed.append("Scenario probe failed.")
            for passed in _string_list(scenario_probe.get("tests_passed")):
                browser.tests_passed.append(passed)
            for failed in _string_list(scenario_probe.get("tests_failed")):
                browser.tests_failed.append(failed)
        browser.evidence.extend(_string_list(runner_result.get("evidence")))
        browser.tests_failed.extend(_string_list(runner_result.get("tests_failed")))
        if runner_result.get("status") not in {None, "", "completed"}:
            browser.status = "failed"
            browser.summary = str(runner_result.get("summary") or "Browser artifact evidence failed.")
        if browser.tests_failed:
            browser.status = "failed"
            browser.summary = "Browser artifact evidence failed."
            browser.tests_passed = []
        return browser


def compute_image_diff(initial: str | Path, after: str | Path) -> dict[str, object]:
    try:
        from PIL import Image, ImageChops, ImageStat
    except ImportError:
        return {"changed_pixels": 0, "error": "Pillow is not installed."}

    first = Image.open(initial).convert("RGB")
    second = Image.open(after).convert("RGB")
    if first.size != second.size:
        return {
            "changed_pixels": 0,
            "error": f"Screenshot sizes differ: {first.size} != {second.size}.",
        }
    diff = ImageChops.difference(first, second)
    stat = ImageStat.Stat(diff)
    data = diff.tobytes()
    changed = sum(1 for index in range(0, len(data), 3) if data[index : index + 3] != b"\x00\x00\x00")
    bbox = diff.getbbox()
    return {
        "changed_pixels": changed,
        "mean_diff": [round(value, 4) for value in stat.mean],
        "bbox": list(bbox) if bbox else [],
    }


def image_is_uniform(path: str | Path) -> bool:
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return False

    image = Image.open(path).convert("RGB")
    reference = Image.new("RGB", image.size, image.getpixel((0, 0)))
    return ImageChops.difference(image, reference).getbbox() is None


def playwright_browser_runner(request: dict[str, object]) -> dict[str, object]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "status": "failed",
            "summary": "Playwright is not installed; automatic browser verification could not run.",
            "tests_failed": ["Playwright is not installed."],
        }

    url = str(request["url"])
    initial = str(request["initial_screenshot"])
    after = str(request["after_interaction_screenshot"])
    profile = str(request.get("profile_name") or "unknown")
    timeout_ms = int(float(request.get("timeout_seconds") or 15) * 1000)
    console_errors: list[str] = []
    evidence: list[str] = []
    gameplay_probe: dict[str, object] = {}
    semantic_probe: dict[str, object] = {}
    scenario_probe: dict[str, object] = {}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 960, "height": 640})
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
            page.on("pageerror", lambda exc: console_errors.append(str(exc)))
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            page.screenshot(path=initial, full_page=True)
            _perform_browser_interactions(page, profile)
            if profile == "canvas_game":
                gameplay_probe = run_canvas_gameplay_probe(page)
            elif profile == "static_web_app":
                semantic_probe = run_static_web_semantic_probe(page)
                scenario_probe = run_acceptance_scenario_probe(
                    page,
                    _scenario_list(request.get("acceptance_scenarios")),
                )
            page.screenshot(path=after, full_page=True)
            browser.close()
        evidence.append("Playwright browser smoke completed.")
        return {
            "status": "completed",
            "console_errors": console_errors,
            "evidence": evidence,
            "semantic_probe": gameplay_probe or semantic_probe,
            "scenario_probe": scenario_probe,
            "gameplay_probe": gameplay_probe,
        }
    except Exception as exc:  # pragma: no cover - depends on local browser installation
        return {
            "status": "failed",
            "summary": f"Playwright browser smoke failed: {exc}",
            "console_errors": console_errors,
            "tests_failed": [str(exc)],
            "evidence": evidence,
            "semantic_probe": gameplay_probe or semantic_probe,
            "scenario_probe": scenario_probe,
            "gameplay_probe": gameplay_probe,
        }


def run_canvas_gameplay_probe(page: object) -> dict[str, object]:
    """Exercise a generated canvas game through the Alchemy test-hook contract."""

    failures: list[str] = []
    passed: list[str] = []
    evidence: list[str] = []

    hook = page.evaluate(
        """() => {
            const api = window.__ALCHEMY_GAME_TEST__;
            if (!api || typeof api.snapshot !== "function") {
              return { available: false };
            }
            const snap = api.snapshot();
            return { available: true, snapshot: snap || {} };
        }"""
    )
    if not isinstance(hook, dict) or not hook.get("available"):
        return {
            "status": "failed",
            "summary": "Canvas game did not expose window.__ALCHEMY_GAME_TEST__.snapshot().",
            "tests_failed": ["Missing window.__ALCHEMY_GAME_TEST__.snapshot() gameplay probe hook."],
            "tests_passed": [],
            "evidence": [],
        }

    initial = hook.get("snapshot", {}) if isinstance(hook.get("snapshot"), dict) else {}
    if _number(initial.get("player_x")) is None:
        failures.append("Gameplay snapshot is missing numeric player_x.")
    else:
        passed.append("Gameplay snapshot exposes player_x.")
    if _number(initial.get("player_y")) is None:
        failures.append("Gameplay snapshot is missing numeric player_y.")
    else:
        passed.append("Gameplay snapshot exposes player_y.")
    state = str(initial.get("state", "") or "")
    if state:
        passed.append("Gameplay snapshot exposes state.")
    else:
        failures.append("Gameplay snapshot is missing state.")

    movement = page.evaluate(
        """async () => {
            const api = window.__ALCHEMY_GAME_TEST__;
            // Canvas games commonly open on a title screen.  The public
            // restart contract is the deterministic way to enter a playable
            // state without guessing at app-specific title-screen controls.
            const restarted = typeof api.restart === "function" ? api.restart() : null;
            const before = restarted && typeof restarted === "object" ? restarted : api.snapshot();
            window.dispatchEvent(new KeyboardEvent("keydown", { code: "ArrowRight", key: "ArrowRight" }));
            for (let i = 0; i < 12; i += 1) {
              if (typeof api.step === "function") {
                api.step(1 / 60);
              }
              await new Promise((resolve) => requestAnimationFrame(resolve));
            }
            window.dispatchEvent(new KeyboardEvent("keyup", { code: "ArrowRight", key: "ArrowRight" }));
            const afterMove = api.snapshot();
            window.dispatchEvent(new KeyboardEvent("keydown", { code: "Space", key: " " }));
            for (let i = 0; i < 16; i += 1) {
              if (typeof api.step === "function") {
                api.step(1 / 60);
              }
              await new Promise((resolve) => requestAnimationFrame(resolve));
            }
            window.dispatchEvent(new KeyboardEvent("keyup", { code: "Space", key: " " }));
            const afterJump = api.snapshot();
            return { before, afterMove, afterJump };
        }"""
    )
    before = movement.get("before", {}) if isinstance(movement, dict) and isinstance(movement.get("before"), dict) else {}
    after_move = movement.get("afterMove", {}) if isinstance(movement, dict) and isinstance(movement.get("afterMove"), dict) else {}
    after_jump = movement.get("afterJump", {}) if isinstance(movement, dict) and isinstance(movement.get("afterJump"), dict) else {}
    before_x = _number(before.get("player_x"))
    moved_x = _number(after_move.get("player_x"))
    before_y = _number(before.get("player_y"))
    jumped_y = _number(after_jump.get("player_y"))
    # Twelve fixed 60 Hz samples are intentionally short: a responsive game
    # should show directional progress, but it need not travel a full world
    # unit while acceleration ramps up.  Require observable positive motion
    # instead of imposing arbitrary level-scale units on every canvas game.
    if before_x is not None and moved_x is not None and moved_x > before_x + 0.01:
        passed.append("Right movement changes player_x.")
        evidence.append(f"player_x moved from {before_x:.2f} to {moved_x:.2f}.")
    else:
        failures.append("Right movement did not increase player_x.")
    if before_y is not None and jumped_y is not None and abs(jumped_y - before_y) > 0.5:
        passed.append("Jump input changes player_y.")
        evidence.append(f"player_y changed from {before_y:.2f} to {jumped_y:.2f}.")
    else:
        failures.append("Jump input did not change player_y.")

    victory = page.evaluate(
        """async () => {
            const api = window.__ALCHEMY_GAME_TEST__;
            if (typeof api.advanceToVictory !== "function") {
              return { supported: false };
            }
            const result = api.advanceToVictory();
            await new Promise((resolve) => requestAnimationFrame(resolve));
            return { supported: true, result: result || {}, snapshot: api.snapshot() || {} };
        }"""
    )
    if isinstance(victory, dict) and victory.get("supported"):
        snapshot = victory.get("snapshot", {}) if isinstance(victory.get("snapshot"), dict) else {}
        victory_state = str(snapshot.get("state", "") or "")
        victory_flag = bool(snapshot.get("won") or victory_state in {"won", "victory", "complete", "completed"})
        if victory_flag:
            passed.append("Victory path can be reached through gameplay probe.")
            evidence.append(f"Victory state reached: {victory_state or 'won'}.")
        else:
            failures.append("advanceToVictory did not produce a winning state.")
    else:
        failures.append("Gameplay probe is missing advanceToVictory().")

    restart = page.evaluate(
        """() => {
            const api = window.__ALCHEMY_GAME_TEST__;
            if (typeof api.restart !== "function") {
              return { supported: false };
            }
            api.restart();
            return { supported: true, snapshot: api.snapshot() || {} };
        }"""
    )
    if isinstance(restart, dict) and restart.get("supported"):
        snapshot = restart.get("snapshot", {}) if isinstance(restart.get("snapshot"), dict) else {}
        restart_state = str(snapshot.get("state", "") or "")
        if restart_state in {"playing", "ready", "running"} or snapshot.get("paused") is False:
            passed.append("Restart returns the game to a playable state.")
            evidence.append(f"Restart state: {restart_state or 'state-reported'}.")
        else:
            failures.append("restart() did not return to a playable state.")
    else:
        failures.append("Gameplay probe is missing restart().")

    return {
        "status": "failed" if failures else "completed",
        "summary": "Canvas gameplay probe passed." if not failures else "Canvas gameplay probe failed.",
        "tests_passed": passed,
        "tests_failed": failures,
        "evidence": evidence,
        "snapshots": {
            "initial": initial,
            "after_move": after_move,
            "after_jump": after_jump,
        },
    }


def run_static_web_semantic_probe(page: object) -> dict[str, object]:
    """Exercise generic static web controls without domain-specific assumptions."""

    result = page.evaluate(
        """async () => {
            const visibleText = () => (document.body?.innerText || "").replace(/\\s+/g, " ").trim();
            const before = {
              title: document.title || "",
              url: location.href,
              text: visibleText(),
              htmlLength: document.body ? document.body.innerHTML.length : 0
            };
            const controls = Array.from(document.querySelectorAll(
              "input, textarea, select, button, a[href], [role='button'], [data-action], [onclick]"
            )).filter((node) => {
              const style = window.getComputedStyle(node);
              return style.visibility !== "hidden" && style.display !== "none" && !node.disabled;
            });
            const inputs = Array.from(document.querySelectorAll("input, textarea, select")).filter((node) => !node.disabled);
            const filled = [];
            for (const node of inputs.slice(0, 3)) {
              const tag = node.tagName.toLowerCase();
              const type = (node.getAttribute("type") || "text").toLowerCase();
              if (tag === "select") {
                if (node.options && node.options.length > 1) {
                  node.selectedIndex = 1;
                  node.dispatchEvent(new Event("change", { bubbles: true }));
                  filled.push(node.name || node.id || "select");
                }
                continue;
              }
              if (type === "checkbox" || type === "radio") {
                node.checked = true;
                node.dispatchEvent(new Event("change", { bubbles: true }));
                filled.push(node.name || node.id || type);
                continue;
              }
              if (["text", "search", "email", "password", "url", "tel", "number", ""].includes(type) || tag === "textarea") {
                node.focus();
                node.value = type === "number" ? "42" : "alchemy semantic probe";
                node.dispatchEvent(new InputEvent("input", { bubbles: true, data: node.value }));
                node.dispatchEvent(new Event("change", { bubbles: true }));
                filled.push(node.name || node.id || type || tag);
              }
            }
            const button = controls.find((node) => {
              const tag = node.tagName.toLowerCase();
              const type = (node.getAttribute("type") || "").toLowerCase();
              const role = (node.getAttribute("role") || "").toLowerCase();
              const isClickable =
                tag === "button" ||
                tag === "a" ||
                (tag === "input" && ["button", "submit"].includes(type)) ||
                role === "button" ||
                node.hasAttribute("data-action") ||
                node.hasAttribute("onclick");
              if (!isClickable) return false;
              const text = (node.innerText || node.value || node.getAttribute("aria-label") || "").toLowerCase();
              if (tag === "a" && node.getAttribute("href") && !node.getAttribute("href").startsWith("#")) return false;
              return !/(delete|remove|logout|sign out|reset|清空|删除|退出)/i.test(text);
            });
            let clicked = "";
            if (button) {
              clicked = button.innerText || button.value || button.getAttribute("aria-label") || button.tagName.toLowerCase();
              button.click();
              await new Promise((resolve) => setTimeout(resolve, 200));
            }
            const after = {
              title: document.title || "",
              url: location.href,
              text: visibleText(),
              htmlLength: document.body ? document.body.innerHTML.length : 0
            };
            return {
              before,
              after,
              counts: {
                controls: controls.length,
                inputs: inputs.length,
                filled: filled.length
              },
              filled,
              clicked,
              changed: before.text !== after.text || before.htmlLength !== after.htmlLength || before.url !== after.url
            };
        }"""
    )
    failures: list[str] = []
    passed: list[str] = []
    evidence: list[str] = []
    if not isinstance(result, dict):
        return {
            "status": "failed",
            "kind": "static_web_app",
            "summary": "Static web semantic probe did not return structured evidence.",
            "tests_passed": [],
            "tests_failed": ["Static web semantic probe did not return structured evidence."],
            "evidence": [],
            "snapshots": {},
        }
    counts = result.get("counts", {}) if isinstance(result.get("counts"), dict) else {}
    controls = int(counts.get("controls", 0) or 0)
    filled = int(counts.get("filled", 0) or 0)
    clicked = str(result.get("clicked", "") or "")
    changed = bool(result.get("changed"))
    if controls:
        passed.append("Static web controls are discoverable.")
        evidence.append(f"{controls} visible control(s) discovered.")
    else:
        passed.append("Static web page has no visible interactive controls.")
        evidence.append("No visible interactive controls were discovered.")
    if filled:
        passed.append("Static web form inputs accept deterministic values.")
        evidence.append(f"{filled} input control(s) filled.")
    if clicked:
        passed.append("Static web clickable control can be activated.")
        evidence.append(f"Clicked control: {clicked}.")
    if controls and (filled or clicked):
        if changed:
            passed.append("Static web interaction changed visible page state.")
            evidence.append("DOM text, HTML length, or URL changed after interaction.")
        else:
            evidence.append("Interaction completed without a visible DOM state change.")
    elif controls and not (filled or clicked):
        failures.append("Static web controls were discovered but none could be safely exercised.")

    return {
        "status": "failed" if failures else "completed",
        "kind": "static_web_app",
        "summary": "Static web semantic probe passed." if not failures else "Static web semantic probe failed.",
        "tests_passed": passed,
        "tests_failed": failures,
        "evidence": evidence,
        "snapshots": {
            "before": result.get("before", {}),
            "after": result.get("after", {}),
            "counts": counts,
            "filled": result.get("filled", []),
            "clicked": clicked,
            "changed": changed,
        },
    }


def run_acceptance_scenario_probe(page: object, scenarios: list[dict[str, object]]) -> dict[str, object]:
    """Run deterministic checks for scenarios inferred from acceptance documents."""

    if not scenarios:
        return {
            "status": "skipped",
            "summary": "No domain-specific acceptance scenarios were provided.",
            "tests_passed": [],
            "tests_failed": [],
            "evidence": [],
            "scenarios": [],
        }
    result = page.evaluate(
        """async (scenarios) => {
            const visibleText = () => (document.body?.innerText || "").replace(/\\s+/g, " ").trim();
            const controls = Array.from(document.querySelectorAll(
              "input, textarea, select, button, a[href], [role='button'], [data-action], [onclick], form"
            )).filter((node) => {
              const style = window.getComputedStyle(node);
              return style.visibility !== "hidden" && style.display !== "none" && !node.disabled;
            });
            const labelFor = (node) => (
              node.innerText ||
              node.value ||
              node.name ||
              node.id ||
              node.getAttribute("aria-label") ||
              node.getAttribute("placeholder") ||
              node.getAttribute("type") ||
              node.tagName
            ).toLowerCase();
            const labels = controls.map(labelFor);
            const inputs = Array.from(document.querySelectorAll("input, textarea, select")).filter((node) => !node.disabled);
            const buttons = Array.from(document.querySelectorAll("button, input[type='button'], input[type='submit'], [role='button'], [data-action], [onclick], a[href^='#']")).filter((node) => !node.disabled);
            const scenarioResults = [];
            for (const scenario of scenarios) {
              const kind = scenario.kind || "";
              const behaviors = Array.isArray(scenario.required_behaviors) ? scenario.required_behaviors : [];
              const passed = [];
              const failed = [];
              const evidence = [];
              if (kind === "crud") {
                const hasInput = inputs.some((node) => !["hidden", "file"].includes((node.getAttribute("type") || "").toLowerCase()));
                const hasCreate = labels.some((text) => /(add|create|new|save|submit|新增|添加|创建|保存)/i.test(text)) || buttons.length > 0;
                const hasList = /(todo|task|item|record|list|table|待办|任务|记录|列表)/i.test(visibleText()) || document.querySelectorAll("li, tr, article, [data-item], [data-record]").length > 0;
                if (hasInput && hasCreate) passed.push("CRUD create controls are present."); else failed.push("CRUD create controls are missing.");
                if (!behaviors.includes("list") || hasList) passed.push("CRUD list/read surface is present."); else failed.push("CRUD list/read surface is missing.");
                if (behaviors.includes("update")) {
                  if (labels.some((text) => /(edit|update|modify|编辑|修改|更新)/i.test(text))) passed.push("CRUD update control is present."); else failed.push("CRUD update control is missing.");
                }
                if (behaviors.includes("delete")) {
                  if (labels.some((text) => /(delete|remove|archive|删除|移除)/i.test(text))) passed.push("CRUD delete control is present."); else failed.push("CRUD delete control is missing.");
                }
                evidence.push(`${inputs.length} input(s), ${buttons.length} clickable control(s).`);
              } else if (kind === "auth") {
                const hasCredentialInput = inputs.some((node) => {
                  const type = (node.getAttribute("type") || "").toLowerCase();
                  const label = labelFor(node);
                  return ["email", "password", "text"].includes(type) || /(email|user|name|password|邮箱|用户|密码)/i.test(label);
                });
                const hasPassword = inputs.some((node) => (node.getAttribute("type") || "").toLowerCase() === "password" || /(password|密码)/i.test(labelFor(node)));
                const hasSubmit = labels.some((text) => /(login|sign in|signin|register|sign up|submit|登录|注册)/i.test(text)) || buttons.length > 0;
                if (hasCredentialInput) passed.push("Authentication credential input is present."); else failed.push("Authentication credential input is missing.");
                if (!behaviors.includes("login") || hasPassword) passed.push("Authentication password/session field is present."); else failed.push("Authentication password field is missing.");
                if (hasSubmit) passed.push("Authentication submit control is present."); else failed.push("Authentication submit control is missing.");
              } else if (kind === "file_upload") {
                const hasFileInput = inputs.some((node) => (node.getAttribute("type") || "").toLowerCase() === "file");
                const hasUploadControl = labels.some((text) => /(upload|import|attach|choose file|上传|导入|附件|文件)/i.test(text));
                if (hasFileInput || hasUploadControl) passed.push("File upload control is present."); else failed.push("File upload control is missing.");
              } else if (kind === "dashboard") {
                const text = visibleText();
                const hasMetric = /(dashboard|analytics|metric|kpi|chart|graph|report|total|count|仪表盘|看板|统计|指标|图表|报表)/i.test(text) || document.querySelectorAll("canvas, svg, table, [data-metric], [data-chart]").length > 0;
                const hasFilter = labels.some((value) => /(filter|search|sort|筛选|搜索|排序)/i.test(value)) || inputs.length > 0;
                if (hasMetric) passed.push("Dashboard metric/report surface is present."); else failed.push("Dashboard metric/report surface is missing.");
                if (!behaviors.includes("filter") || hasFilter) passed.push("Dashboard filter/search control is present."); else failed.push("Dashboard filter/search control is missing.");
              }
              scenarioResults.push({
                id: scenario.id || "",
                kind,
                title: scenario.title || "",
                tests_passed: passed,
                tests_failed: failed,
                evidence
              });
            }
            return {
              text: visibleText(),
              controls: controls.length,
              inputs: inputs.length,
              buttons: buttons.length,
              scenarios: scenarioResults
            };
        }""",
        scenarios,
    )
    if not isinstance(result, dict):
        return {
            "status": "failed",
            "summary": "Acceptance scenario probe did not return structured evidence.",
            "tests_passed": [],
            "tests_failed": ["Acceptance scenario probe did not return structured evidence."],
            "evidence": [],
            "scenarios": [],
        }
    scenario_results = result.get("scenarios", []) if isinstance(result.get("scenarios"), list) else []
    passed: list[str] = []
    failures: list[str] = []
    evidence: list[str] = [
        f"{len(scenario_results)} scenario(s) evaluated.",
        f"{int(result.get('controls', 0) or 0)} visible control(s) available.",
    ]
    for scenario in scenario_results:
        if not isinstance(scenario, dict):
            continue
        prefix = f"{scenario.get('id') or scenario.get('kind')}: "
        passed.extend(prefix + value for value in _string_list(scenario.get("tests_passed")))
        failures.extend(prefix + value for value in _string_list(scenario.get("tests_failed")))
        evidence.extend(prefix + value for value in _string_list(scenario.get("evidence")))
    return {
        "status": "failed" if failures else "completed",
        "summary": "Acceptance scenario probe passed." if not failures else "Acceptance scenario probe failed.",
        "tests_passed": passed,
        "tests_failed": failures,
        "evidence": evidence,
        "scenarios": scenario_results,
    }


def _perform_browser_interactions(page: object, profile_name: str) -> None:
    if profile_name == "canvas_game":
        try:
            page.locator("canvas").first.click(timeout=1000)
        except Exception:
            page.mouse.click(200, 200)
        for key in ("ArrowRight", "Space", "ArrowRight"):
            page.keyboard.press(key)
            page.wait_for_timeout(150)
        return
    page.mouse.move(200, 200)
    page.wait_for_timeout(300)


def _number(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _scenario_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def static_web_root_present(html: str) -> bool:
    lowered = html.lower()
    return any(marker in lowered for marker in ("<main", "<form", "<section", "<article", "id=\"app\"", "id='app'", "role=\"main\"", "role='main'"))


def static_web_controls_present(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "<button",
            "<input",
            "<textarea",
            "<select",
            "role=\"button\"",
            "role='button'",
            "onclick",
            "data-action",
        )
    )


def _start_static_server(repo: Path) -> ThreadingHTTPServer:
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

    handler = partial(QuietHandler, directory=str(repo))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _resolve_evidence_path(output_dir: Path, value: str | Path) -> Path | None:
    if not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = output_dir / candidate
    return candidate if candidate.exists() and candidate.is_file() else None


def dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return [str(value)]
