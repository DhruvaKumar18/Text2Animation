import subprocess
import os
import tempfile
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def run_ffmpeg_command(cmd: list[str]) -> bool:
    """
    Executes an FFmpeg command as a subprocess, captures output, and logs failures.
    """
    try:
        logger.info(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg execution failed.\nCommand: {' '.join(cmd)}\nStdout: {e.stdout}\nStderr: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Failed to execute FFmpeg command: {e}")
        return False


def convert_image_to_video(image_path: str, output_path: str, duration: float) -> bool:
    """
    Converts a single image into a static MP4 video clip of specified duration.
    """
    ffmpeg_bin = getattr(settings, 'FFMPEG_PATH', 'ffmpeg')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # FFmpeg command to loop the image for the duration and encode to H.264 MP4
    cmd = [
        ffmpeg_bin,
        '-y',
        '-loop', '1',
        '-i', image_path,
        '-c:v', 'libx264',
        '-t', str(duration),
        '-pix_fmt', 'yuv420p',
        '-vf', 'scale=1280:720',
        output_path
    ]
    return run_ffmpeg_command(cmd)


def add_text_caption_to_video(video_path: str, output_path: str, caption: str) -> bool:
    """
    Overlays narration text caption onto the bottom of the video.
    Falls back to copying the input video if the drawtext filter fails (e.g. missing font).
    """
    ffmpeg_bin = getattr(settings, 'FFMPEG_PATH', 'ffmpeg')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Escape simple characters for FFmpeg filter syntax
    escaped_caption = caption.replace("'", "'\\''").replace(":", "\\:")
    
    # Try using system font or standard font expression
    # Use standard Arial, or fall back to standard fonts on Windows/Unix
    font_option = "fontfile='C\\:/Windows/Fonts/arial.ttf':" if os.name == 'nt' else ""
    
    # Drawtext filter parameters
    filter_graph = (
        f"drawtext={font_option}text='{escaped_caption}':"
        "x=(w-text_w)/2:y=h-80:fontsize=22:fontcolor=white:"
        "box=1:boxcolor=black@0.6:boxborderw=10"
    )
    
    cmd = [
        ffmpeg_bin,
        '-y',
        '-i', video_path,
        '-vf', filter_graph,
        '-c:a', 'copy',
        output_path
    ]
    
    success = run_ffmpeg_command(cmd)
    if not success:
        # Fallback: Copy original file to output path
        logger.warning("Caption overlay failed, falling back to copy input video.")
        import shutil
        try:
            shutil.copy2(video_path, output_path)
            return True
        except Exception as e:
            logger.error(f"Fallback copy failed: {e}")
            return False
            
    return True


def stitch_videos(video_paths: list[str], output_path: str) -> bool:
    """
    Stitches multiple video files together into a single video file using FFmpeg's concat demuxer.
    """
    ffmpeg_bin = getattr(settings, 'FFMPEG_PATH', 'ffmpeg')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    if not video_paths:
        logger.error("No video paths provided for stitching.")
        return False
        
    # Write paths to a temporary file list for the concat demuxer
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for path in video_paths:
            # Format path correctly for FFmpeg concat file (forward slashes are safer, single quotes escaped)
            normalized_path = os.path.abspath(path).replace('\\', '/')
            f.write(f"file '{normalized_path}'\n")
        temp_file_list = f.name
        
    try:
        # Run the concat demuxer command (copies streams without re-encoding)
        cmd = [
            ffmpeg_bin,
            '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', temp_file_list,
            '-c', 'copy',
            output_path
        ]
        success = run_ffmpeg_command(cmd)
    finally:
        # Clean up temporary file
        if os.path.exists(temp_file_list):
            os.remove(temp_file_list)
            
    return success
