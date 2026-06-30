import glob
import json
import os
import statistics
import time
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image

from src.config import ImageProcessingConfig as imgconfig
from src.config import DebugConfig
from src.logger import logger

__all__ = [
    "find_cost_bar_roi",
    "calibrate",
    "save_calibration_data",
    "load_calibration_by_filename",
    "find_calibration",
    "get_calibration_profiles",
    "get_tick_from_calibration",
]


def _debug(msg: str, *args: Any) -> None:
    """Emit a debug log only if tick-detection logging is enabled."""
    if DebugConfig.LOG_TICK_DETECTION:
        _debug(msg, *args)


# Calibration files are stored under the project root, next to config.json.
_CALIBRATION_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "calibration",
)

# Thresholds for cost bar pixel detection, ported from ArknightsCostBarRuler.
_WHITE_THRESHOLD = 250
_MASKED_WHITE_THRESHOLD = 150
_MASKED_MAX_BRIGHTNESS = 165
_GRAY_TOLERANCE = 20
_ALPHA_OPAQUE = 255

# Tolerance used when looking up a pixel width that is not exactly in the map.
_LOOKUP_TOLERANCE = 5


def _ensure_calibration_dir() -> None:
    if not os.path.exists(_CALIBRATION_DIR):
        logger.info(f"Calibration directory '{_CALIBRATION_DIR}' does not exist, creating...")
        os.makedirs(_CALIBRATION_DIR, exist_ok=True)


def find_cost_bar_roi(screen_width: int, screen_height: int) -> Tuple[int, int, int]:
    """
    Calculate the cost bar ROI for the given screen resolution.

    The ROI is returned as (x1, x2, y_mid) in integer pixel coordinates.
    This mirrors the algorithm used by ArknightsCostBarRuler.
    """
    ref_width, ref_height = 1920.0, 1080.0
    ref_aspect_ratio = ref_width / ref_height
    x1_offset_from_right_ref = ref_width - 1739
    x2_offset_from_right_ref = ref_width - 1919
    y1_offset_from_bottom_ref = ref_height - 810
    y2_offset_from_bottom_ref = ref_height - 817

    current_aspect_ratio = screen_width / screen_height
    if current_aspect_ratio >= ref_aspect_ratio:
        scale = screen_height / ref_height
    else:
        scale = screen_width / ref_width

    x1 = screen_width - x1_offset_from_right_ref * scale
    x2 = screen_width - x2_offset_from_right_ref * scale
    y1 = screen_height - y1_offset_from_bottom_ref * scale
    y2 = screen_height - y2_offset_from_bottom_ref * scale

    x1_int, x2_int = round(x1), round(x2)
    y_mid_int = round((y1 + y2) / 2)
    _debug(
        f"Cost bar ROI for {screen_width}x{screen_height}: "
        f"x1={x1_int}, x2={x2_int}, y={y_mid_int}"
    )
    return x1_int, x2_int, y_mid_int


def _is_pixel_grayscale(r: int, g: int, b: int) -> bool:
    return abs(r - g) <= _GRAY_TOLERANCE and abs(g - b) <= _GRAY_TOLERANCE


def _get_raw_filled_pixel_width(
    frame: Image.Image,
    roi: Tuple[int, int, int],
    dump_prefix: Optional[str] = None,
) -> Optional[int]:
    """
    Extract the filled pixel width from the cost bar ROI.

    Returns the width in pixels, or None if the ROI does not look like a cost bar.
    Supports both normal and masked (dimmed) cost bar modes.
    """
    x1, x2, y = roi
    total_width = x2 - x1
    if total_width <= 0:
        return None

    if frame.mode != "RGBA":
        frame = frame.convert("RGBA")

    # Quick sanity check on the right-most pixel.
    try:
        r_end, g_end, b_end, a_end = frame.getpixel((x2 - 1, y))
    except IndexError:
        logger.warning(f"ROI out of image bounds: roi={roi}, image_size={frame.size}")
        return None

    if a_end != _ALPHA_OPAQUE and not _is_pixel_grayscale(r_end, g_end, b_end):
        _debug("ROI invalid: end pixel is not opaque grayscale.")
        return None

    # Normal bright cost bar detection.
    filled_width = 0
    is_end_pixel_white = all(c >= _WHITE_THRESHOLD for c in (r_end, g_end, b_end))
    if is_end_pixel_white:
        filled_width = total_width
    else:
        for x in range(x2 - 2, x1, -1):
            r, g, b, a = frame.getpixel((x, y))
            if a != _ALPHA_OPAQUE and not _is_pixel_grayscale(r, g, b):
                _debug(f"ROI invalid pixel at x={x}, aborting normal detection.")
                return None

            is_current_pixel_white = all(c >= _WHITE_THRESHOLD for c in (r, g, b))
            if is_current_pixel_white:
                filled_width = x - x1 + 1
                break

    if filled_width > 0:
        _debug(f"Normal mode cost bar filled width: {filled_width}")
        return filled_width

    # Fallback to masked (dimmed) mode detection.
    _debug("Falling back to masked mode detection.")
    is_end_pixel_masked_white = all(c >= _MASKED_WHITE_THRESHOLD for c in (r_end, g_end, b_end))
    if is_end_pixel_masked_white:
        filled_width = total_width
    else:
        for x in range(x2 - 2, x1, -1):
            r, g, b, a = frame.getpixel((x, y))
            # In masked mode no pixel should be too bright and all should be grayscale.
            if a != _ALPHA_OPAQUE and (
                not _is_pixel_grayscale(r, g, b) or any(c > _MASKED_MAX_BRIGHTNESS for c in (r, g, b))
            ):
                _debug(f"Masked mode invalid/too-bright pixel at x={x}, aborting.")
                filled_width = 0
                break

            is_current_pixel_masked_white = all(c >= _MASKED_WHITE_THRESHOLD for c in (r, g, b))
            if is_current_pixel_masked_white:
                filled_width = x - x1 + 1
                break

    _debug(f"Cost bar filled width: {filled_width}")
    return filled_width


def _calculate_jaccard_similarity(set1: set, set2: set) -> float:
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
    return len(set1.intersection(set2)) / len(set1.union(set2))


def calibrate(
    capture_func: Callable[[], Image.Image],
    screen_width: int,
    screen_height: int,
    num_cycles: int = 6,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> Dict[str, Any]:
    """
    Perform cost bar calibration.

    `capture_func` should return a PIL Image (RGB/RGBA) of the game at a
    fixed resolution (`screen_width` x `screen_height`).  In the prts-plus
    pipeline this is normally the standardized 1280x720 frame obtained from
    `capture_game_window(ratio=None)`.

    Collects several cost cycles, clusters them, and builds one or more
    pixel-width -> tick profiles.  Returns a dict ready to be saved by
    `save_calibration_data`.
    """
    logger.info(f"Starting cost bar calibration at {screen_width}x{screen_height}, target cycles: {num_cycles}.")
    cycle_samples: List[List[int]] = []
    current_cycle_data: List[int] = []
    previous_cost_state_raw: Optional[int] = None
    is_collecting_cycle = False
    calibration_frame_count = 0

    frame = capture_func()
    width, height = frame.size
    if (width, height) != (screen_width, screen_height):
        logger.warning(
            f"Capture resolution {width}x{height} differs from expected "
            f"{screen_width}x{screen_height}. Calibration will use the actual capture size."
        )
        screen_width, screen_height = width, height

    logger.info("Collecting cost bar cycle samples...")
    while len(cycle_samples) < num_cycles:
        try:
            frame = capture_func()
            calibration_frame_count += 1

            roi = find_cost_bar_roi(screen_width, screen_height)
            current_cost_state_raw = _get_raw_filled_pixel_width(
                frame,
                roi,
                dump_prefix=f"calib_frame_{calibration_frame_count}",
            )

            total_bar_width = roi[1] - roi[0]
            if current_cost_state_raw is not None and total_bar_width > 0:
                current_fill_percentage = current_cost_state_raw / total_bar_width
            else:
                current_fill_percentage = 0.0

            overall_progress = (len(cycle_samples) + current_fill_percentage) / num_cycles
            progress_percent = min(100.0, overall_progress * 100)
            if progress_callback:
                progress_callback(progress_percent)

            if current_cost_state_raw is None:
                previous_cost_state_raw = None
                continue

            if previous_cost_state_raw is not None and total_bar_width > 0:
                if previous_cost_state_raw > total_bar_width * 0.9 and current_cost_state_raw < total_bar_width * 0.1:
                    is_collecting_cycle = True
                    if current_cycle_data:
                        cycle_samples.append(current_cycle_data)
                        logger.info(
                            f"Collected a full cycle ({len(current_cycle_data)} frames), "
                            f"{len(cycle_samples)}/{num_cycles} done."
                        )
                        current_cycle_data = []

            if is_collecting_cycle:
                current_cycle_data.append(current_cost_state_raw)

            previous_cost_state_raw = current_cost_state_raw

        except Exception as e:
            logger.exception(f"Calibration error: {e}. Retrying in 1 second...")
            time.sleep(1)
            previous_cost_state_raw = None

    logger.info("Data collection complete. Starting clustering and modeling.")

    if not cycle_samples:
        raise RuntimeError("No valid cost cycles collected. Make sure the game is running at normal speed.")

    clusters: List[List[List[int]]] = []
    similarity_threshold = 0.8

    for sample in cycle_samples:
        sample_set = set(sample)
        if not sample_set:
            continue

        best_match_index = -1
        max_similarity = -1
        for i, cluster in enumerate(clusters):
            representative_set = set(cluster[0])
            similarity = _calculate_jaccard_similarity(sample_set, representative_set)
            if similarity > max_similarity:
                max_similarity = similarity
                best_match_index = i

        if max_similarity >= similarity_threshold:
            _debug(f"Sample matches cluster {best_match_index} (similarity {max_similarity:.2f}).")
            clusters[best_match_index].append(sample)
        else:
            logger.info(f"Creating new cluster (best similarity {max_similarity:.2f}).")
            clusters.append([sample])

    logger.info(f"Clustering complete: {len(clusters)} cost cycle model(s).")

    final_profiles = []
    for i, cluster in enumerate(clusters):
        logger.info(f"--- Analyzing model {i + 1} ({len(cluster)} samples) ---")
        merged_widths = [w for sample in cluster for w in sample]
        width_counts = Counter(merged_widths)

        # Hidden glow frame detection.
        count_zero = width_counts.get(0, 0)
        non_zero_counts = [count for width, count in width_counts.items() if width > 0]
        num_hidden_frames = 0
        if non_zero_counts:
            median_count = statistics.median(non_zero_counts)
            outlier_threshold = median_count * 5
            filtered_counts = [count for count in non_zero_counts if count < outlier_threshold]
            if filtered_counts:
                baseline_frequency = statistics.median(filtered_counts)
                logger.info(f"Model {i + 1}: baseline frequency ≈ {baseline_frequency:.2f} samples/frame")
                if baseline_frequency > 0:
                    num_frames_in_empty_state = round(count_zero / baseline_frequency)
                    num_hidden_frames = max(0, num_frames_in_empty_state - 1)
                    if num_hidden_frames > 0:
                        logger.warning(f"Model {i + 1}: detected {num_hidden_frames} hidden glow frames.")
            else:
                logger.warning(f"Model {i + 1}: no stable frequency, cannot detect hidden frames.")
        else:
            logger.warning(f"Model {i + 1}: no non-zero states collected.")

        unique_pixel_widths = sorted(width_counts.keys())
        pixel_to_frame_map = {}
        total_frames = len(unique_pixel_widths) + num_hidden_frames

        if 0 in unique_pixel_widths:
            pixel_to_frame_map[str(0)] = 0

        frame_offset = 1 + num_hidden_frames
        non_zero_widths = [w for w in unique_pixel_widths if w > 0]
        for idx, pixel_width in enumerate(non_zero_widths):
            logical_frame = idx + frame_offset
            pixel_to_frame_map[str(pixel_width)] = logical_frame

        final_profiles.append({
            "total_frames": total_frames,
            "pixel_map": pixel_to_frame_map,
        })
        logger.info(f"Model {i + 1} built, total frames: {total_frames}.")

    if not final_profiles:
        raise RuntimeError("Calibration failed: could not build any valid cost cycle model.")

    calibrated_data = {
        "detection_mode": "alternating" if len(final_profiles) > 1 else "single",
        "profiles": final_profiles,
        "screen_width": screen_width,
        "screen_height": screen_height,
    }
    logger.info("Calibration completed successfully.")
    return calibrated_data


def save_calibration_data(
    data: Dict[str, Any],
    screen_width: int,
    screen_height: int,
    basename: str = "default",
) -> str:
    """Save calibration data and return the filename used."""
    _ensure_calibration_dir()
    profiles = data.get("profiles", [])
    if profiles:
        frame_counts_str = "-".join(str(p["total_frames"]) for p in profiles) + "f"
    else:
        frame_counts_str = "0f"

    data["calibration_time"] = time.time()
    filename = f"{basename}_{frame_counts_str}_{screen_width}x{screen_height}.json"
    filepath = os.path.join(_CALIBRATION_DIR, filename)
    logger.info(f"Saving calibration data to '{filepath}'...")
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        logger.info("Calibration data saved.")
    except Exception as e:
        logger.exception(f"Error saving calibration file '{filepath}': {e}")
        raise
    return filename


def load_calibration_by_filename(filename: str) -> Optional[Dict[str, Any]]:
    """Load a calibration file by its filename."""
    filepath = os.path.join(_CALIBRATION_DIR, filename)
    logger.info(f"Loading calibration data: '{filepath}'")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.warning(f"Calibration file '{filepath}' not found.")
        return None
    except json.JSONDecodeError:
        logger.error(f"Calibration file '{filepath}' is corrupted.")
        return None

    is_new_format = "profiles" in data and isinstance(data["profiles"], list)
    is_old_format = "pixel_map" in data

    if is_new_format:
        if all("total_frames" in p and "pixel_map" in p for p in data["profiles"]):
            logger.info("New multi-profile calibration format loaded.")
            return data
        logger.error(f"Calibration file '{filepath}' has incomplete profiles.")
        return None

    if is_old_format:
        logger.warning("Old single-model calibration format detected, converting.")
        return {
            "detection_mode": "single",
            "profiles": [{
                "total_frames": data.get("total_frames"),
                "pixel_map": data.get("pixel_map"),
            }],
            "screen_width": data.get("screen_width"),
            "screen_height": data.get("screen_height"),
            "calibration_time": data.get("calibration_time"),
        }

    logger.error(f"Calibration file '{filepath}' format not recognized.")
    return None


def get_calibration_profiles() -> List[Dict[str, Any]]:
    """List all calibration profiles found in the calibration directory."""
    _ensure_calibration_dir()
    profiles_info = []
    for filepath in glob.glob(os.path.join(_CALIBRATION_DIR, "*.json")):
        filename = os.path.basename(filepath)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "profiles" in data and isinstance(data.get("profiles"), list):
                frame_counts = [p.get("total_frames", "N/A") for p in data["profiles"]]
                total_frames_str = "-".join(map(str, frame_counts)) + "f"
            else:
                total_frames_str = str(data.get("total_frames", "N/A")) + "f"

            profiles_info.append({
                "filename": filename,
                "basename": filename.split("_")[0] if "_" in filename else filename.replace(".json", ""),
                "total_frames_str": total_frames_str,
                "resolution": f"{data.get('screen_width', '?')}x{data.get('screen_height', '?')}",
            })
        except (json.JSONDecodeError, KeyError) as e:
            profiles_info.append({
                "filename": filename,
                "basename": filename.replace(".json", ""),
                "total_frames_str": "corrupted",
                "resolution": "unknown",
            })
            logger.warning(f"Corrupted calibration profile: {filename}, error: {e}")

    profiles_info.sort(key=lambda p: p["filename"])
    logger.info(f"Found {len(profiles_info)} calibration profile(s).")
    return profiles_info


def find_calibration(screen_width: int, screen_height: int) -> Optional[Dict[str, Any]]:
    """
    Find the newest calibration file matching the given resolution.

    Returns the loaded calibration data, or None if no match is found.
    """
    candidates = []
    for profile in get_calibration_profiles():
        if profile["resolution"] == f"{screen_width}x{screen_height}":
            candidates.append(profile)

    if not candidates:
        return None

    # Pick the newest based on file mtime.
    candidates.sort(
        key=lambda p: os.path.getmtime(os.path.join(_CALIBRATION_DIR, p["filename"])),
        reverse=True,
    )
    return load_calibration_by_filename(candidates[0]["filename"])


def get_tick_from_calibration(
    frame: Image.Image,
    roi: Tuple[int, int, int],
    calibration_data: Dict[str, Any],
    dump_prefix: Optional[str] = None,
) -> Optional[int]:
    """
    Map the current cost bar state to a tick value using calibration data.

    Returns a tick in [0, total_frames - 1], or None if detection fails.
    For multi-profile data the first profile is used (sufficient for Step 2).
    """
    profiles = calibration_data.get("profiles")
    if not profiles:
        _debug("Calibration data contains no profiles.")
        return None

    profile = profiles[0]
    pixel_map = profile.get("pixel_map", {})
    if not pixel_map:
        _debug("Calibration profile contains no pixel_map.")
        return None

    current_pixel_width = _get_raw_filled_pixel_width(frame, roi, dump_prefix=dump_prefix)
    if current_pixel_width is None:
        return None

    pixel_key = str(current_pixel_width)
    if pixel_key in pixel_map:
        tick = pixel_map[pixel_key]
        _debug(f"Pixel width {current_pixel_width} -> tick {tick}")
        return tick

    closest_pixel_value = -1
    min_diff = float("inf")
    for pixel_str in pixel_map.keys():
        pixel_val = int(pixel_str)
        diff = abs(current_pixel_width - pixel_val)
        if diff < min_diff:
            min_diff = diff
            closest_pixel_value = pixel_val

    if min_diff <= _LOOKUP_TOLERANCE:
        tick = pixel_map[str(closest_pixel_value)]
        _debug(
            f"Pixel width {current_pixel_width} approximated to {closest_pixel_value} "
            f"(diff {min_diff}) -> tick {tick}"
        )
        return tick

    _debug(f"Pixel width {current_pixel_width} not found in calibration map.")
    return None
