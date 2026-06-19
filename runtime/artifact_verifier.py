"""Deterministic static verification for generated web artifacts."""

from __future__ import annotations

import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .artifact_profile import ArtifactProfile, ArtifactProfileDetector


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
        selected_files = dedupe(files or ["index.html"])
        profile = self.profile_detector.detect(repo, selected_files, objective=objective, requirements=requirements)
        if profile.name not in {"canvas_game", "static_web_app", "unknown"}:
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
            elif "<canvas" not in html.lower() and "game" not in html.lower():
                failures.append("HTML entrypoint does not expose a canvas or game root.")
            else:
                evidence.append("HTML entrypoint exposes a canvas or game root.")

        if "requestanimationframe" in lowered or re.search(r"\bsetinterval\s*\(", lowered):
            evidence.append("Animation or render loop is present.")
        else:
            failures.append("No animation or render loop was detected.")

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
        if isinstance(gameplay_probe, dict) and gameplay_probe:
            browser.gameplay_probe = dict(gameplay_probe)
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
            page.screenshot(path=after, full_page=True)
            browser.close()
        evidence.append("Playwright browser smoke completed.")
        return {
            "status": "completed",
            "console_errors": console_errors,
            "evidence": evidence,
            "gameplay_probe": gameplay_probe,
        }
    except Exception as exc:  # pragma: no cover - depends on local browser installation
        return {
            "status": "failed",
            "summary": f"Playwright browser smoke failed: {exc}",
            "console_errors": console_errors,
            "tests_failed": [str(exc)],
            "evidence": evidence,
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
            const before = api.snapshot();
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
    if before_x is not None and moved_x is not None and moved_x > before_x + 1:
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
        if restart_state in {"playing", "ready", "running"}:
            passed.append("Restart returns the game to a playable state.")
            evidence.append(f"Restart state: {restart_state}.")
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
