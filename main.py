from fastapi import FastAPI, UploadFile, File, Form
import subprocess
import os
import sys
print(sys.path)
print(sys.executable)  # <-- Eklendi

app = FastAPI()

@app.post("/generate_sfx")
async def generate_sfx(
    prompt: str = Form(...),
    duration: int = Form(8),
    video: UploadFile = File(None)
):
    # 1) Kaydetme (eğer video dosyası geldiyse)
    if video:
        video_path = f"./temp_{video.filename}"
        with open(video_path, "wb") as f:
            f.write(await video.read())
    else:
        video_path = None

    # 2) MMAudio demo.py'yi çalıştır
    cmd = [
        sys.executable,  # <-- "python" yerine sys.executable
        "./MMAudioDir/demo.py",
        f"--duration={duration}",
        f"--prompt={prompt}"
    ]
    if video_path:
        cmd.append(f"--video={video_path}")

    # Subprocess
    subprocess.run(cmd, check=True)

    # 3) Output dosyası (MMAudio default -> MMAudioDir/output/audio.flac / video.mp4)
    return {"status": "done", "info": "Check MMAudioDir/output folder"}