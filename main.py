from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pathlib import Path
import yt_dlp
import asyncio
import json
import os

app = FastAPI()

# 设置模板和静态文件
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")

# 确保下载目录存在
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# 存储下载任务状态
download_tasks = {}

def get_video_info(url):
    with yt_dlp.YoutubeDL() as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info["title"],
                "duration": info["duration"],
                "author": info["uploader"],
                "description": info["description"],
                "thumbnail": info["thumbnail"]
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

async def download_video(url, video_id):
    download_tasks[video_id] = {"status": "downloading", "progress": 0}
    
    def progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
            if total > 0:
                download_tasks[video_id]["progress"] = (d['downloaded_bytes'] / total) * 100

    ydl_opts = {
        'format': 'best',
        'outtmpl': str(DOWNLOAD_DIR / '%(title)s.%(ext)s'),
        'progress_hooks': [progress_hook],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = DOWNLOAD_DIR / f"{info['title']}.{info['ext']}"
            
            video_data = {
                "title": info["title"],
                "duration": info["duration"],
                "author": info["uploader"],
                "description": info["description"],
                "file_size": os.path.getsize(file_path),
                "local_path": str(file_path),
                "thumbnail": info["thumbnail"]
            }
            
            # 保存视频信息到 JSON 文件
            with open(DOWNLOAD_DIR / "videos.json", "a+") as f:
                f.seek(0)
                try:
                    videos = json.load(f)
                except json.JSONDecodeError:
                    videos = []
                videos.append(video_data)
                f.seek(0)
                f.truncate()
                json.dump(videos, f)

            download_tasks[video_id]["status"] = "completed"
            download_tasks[video_id]["video_data"] = video_data
    except Exception as e:
        download_tasks[video_id]["status"] = "failed"
        download_tasks[video_id]["error"] = str(e)

@app.get("/")
async def home(request: Request):
    # 读取已下载的视频列表
    try:
        with open(DOWNLOAD_DIR / "videos.json", "r") as f:
            videos = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        videos = []
    
    return templates.TemplateResponse(
        "index.html", 
        {"request": request, "videos": videos}
    )

@app.post("/download")
async def download(request: Request):
    data = await request.json()
    url = data.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    video_id = str(len(download_tasks))
    asyncio.create_task(download_video(url, video_id))
    return {"task_id": video_id}

@app.get("/status/{task_id}")
async def get_status(task_id: str):
    if task_id not in download_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return download_tasks[task_id] 