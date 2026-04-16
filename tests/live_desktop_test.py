"""Live desktop test: open gnome-calculator, interact via xdotool, capture evidence."""

import asyncio
import subprocess
import time
from pathlib import Path

# Bootstrap server config
import interact_mcp.server as server
from interact_mcp.config import Config
from interact_mcp import desktop

OUTPUT = Path("test_output")
OUTPUT.mkdir(exist_ok=True)


async def main():
    # Use a real VLM for element detection — empty means it'll skip VLM analysis
    cfg = Config(
        screenshot_dump_dir=OUTPUT,
        image_model="",  # we'll capture raw screenshots manually
    )
    server.config = cfg

    print("=== LIVE DESKTOP TEST: gnome-calculator ===\n")

    # --- Step 1: Launch gnome-calculator ---
    print("[1] Launching gnome-calculator...")
    proc = subprocess.Popen(
        ["gnome-calculator"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    # Wait for window to appear (may take longer on first launch)
    calc = None
    for _ in range(10):
        time.sleep(1)
        calc = desktop.find_window("calculator")
        if calc:
            break
    if not calc:
        print("ERROR: Calculator window not found after 10s!")
        proc.terminate()
        return
    print(f"    Found: '{calc.name}' wid={calc.wid} ({calc.w}x{calc.h})")

    # --- Step 2: List windows ---
    print("[2] Listing desktop windows...")
    windows = desktop.list_windows()
    for w in windows:
        print(f"    {w.name} ({w.w}x{w.h}) wid={w.wid}")

    # --- Step 3: Screenshot the window ---
    print("\n[3] Taking initial screenshot...")
    png = desktop.capture_window(calc.wid)
    path1 = OUTPUT / "01_calculator_initial.png"
    path1.write_bytes(png)
    print(f"    Saved: {path1} ({len(png)} bytes)")

    # --- Step 4: Type a calculation via xdotool ---
    print("\n[4] Typing calculation: 42 * 13 + 7 =")
    # Use desktop_type for character input (not desktop_key — keysyms behave
    # differently in GTK apps). desktop_key is for control keys (Enter, Tab, etc.)
    await desktop.desktop_type(calc.wid, "42*13+7")
    await asyncio.sleep(0.3)
    await desktop.desktop_key(calc.wid, "Return")
    await asyncio.sleep(0.5)

    # --- Step 5: Screenshot after calculation ---
    print("[5] Taking screenshot after calculation...")
    png2 = desktop.capture_window(calc.wid)
    path2 = OUTPUT / "02_calculator_after_math.png"
    path2.write_bytes(png2)
    print(f"    Saved: {path2} ({len(png2)} bytes)")

    # --- Step 6: Record video while pressing buttons ---
    print("\n[6] Recording video while pressing more buttons...")

    async def press_buttons():
        await asyncio.sleep(0.5)
        await desktop.desktop_key(calc.wid, "Escape")  # clear
        await asyncio.sleep(0.2)
        await desktop.desktop_type(calc.wid, "999+1")
        await asyncio.sleep(0.2)
        await desktop.desktop_key(calc.wid, "Return")
        await asyncio.sleep(0.3)

    # Start recording and button presses concurrently
    video_task = asyncio.get_event_loop().run_in_executor(
        None, desktop.capture_window_video, calc.wid, 4.0, 10
    )
    button_task = asyncio.create_task(press_buttons())
    await button_task
    video_bytes = await video_task

    path_vid = OUTPUT / "03_calculator_video.mp4"
    path_vid.write_bytes(video_bytes)
    print(f"    Saved: {path_vid} ({len(video_bytes)} bytes)")

    # --- Step 7: Check motion detection on the video ---
    print("\n[7] Checking motion detection...")
    has_motion = desktop.detect_motion(video_bytes)
    print(f"    Motion detected: {has_motion}")

    # --- Step 8: Final screenshot ---
    print("\n[8] Final screenshot...")
    png3 = desktop.capture_window(calc.wid)
    path3 = OUTPUT / "04_calculator_final.png"
    path3.write_bytes(png3)
    print(f"    Saved: {path3} ({len(png3)} bytes)")

    # --- Step 9: Test clicking a specific coordinate ---
    print("\n[9] Clicking on the calculator window (center)...")
    cx, cy = calc.w // 2, calc.h // 2
    await desktop.desktop_click(calc.wid, cx, cy)
    await asyncio.sleep(0.3)
    print(f"    Clicked at ({cx}, {cy})")

    # --- Step 10: Test scrolling ---
    print("\n[10] Testing scroll...")
    await desktop.desktop_scroll(calc.wid, cx, cy, "down", 3)
    await asyncio.sleep(0.3)
    print("    Scrolled down 3 clicks")

    # --- Step 11: Test hover ---
    print("\n[11] Testing hover...")
    await desktop.desktop_hover(calc.wid, 10, 10)
    await asyncio.sleep(0.2)
    print("    Hovered at (10, 10)")

    # --- Step 12: Record a static video (nothing happening) ---
    print("\n[12] Recording static video (no interaction)...")
    static_video = desktop.capture_window_video(calc.wid, 2.0, 5)
    path_static = OUTPUT / "05_calculator_static.mp4"
    path_static.write_bytes(static_video)
    static_motion = desktop.detect_motion(static_video)
    print(f"    Saved: {path_static} ({len(static_video)} bytes)")
    print(f"    Motion detected: {static_motion} (should be False)")

    # --- Cleanup ---
    print("\n[13] Cleaning up...")
    proc.terminate()
    proc.wait(timeout=5)
    print("    Calculator closed.")

    # --- Summary ---
    print("\n=== TEST COMPLETE ===")
    print(f"Output files in {OUTPUT}:")
    for f in sorted(OUTPUT.iterdir()):
        print(f"    {f.name} ({f.stat().st_size:,} bytes)")

    print("\nResults:")
    print(f"    Motion video:  {'PASS' if has_motion else 'FAIL'} (expected True)")
    print(
        f"    Static video:  {'PASS' if not static_motion else 'FAIL'} (expected False)"
    )
    all_pass = has_motion and not static_motion
    print(f"    Overall:       {'ALL PASS' if all_pass else 'SOME FAILED'}")


if __name__ == "__main__":
    asyncio.run(main())
