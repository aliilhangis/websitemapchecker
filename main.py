import os
import asyncio
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from xml.etree import ElementTree as ET

app = FastAPI()

MAX_URLS = int(os.getenv("MAX_URLS", 1000))
TIMEOUT = int(os.getenv("TIMEOUT", 10))
CONCURRENCY = int(os.getenv("CONCURRENCY", 20))

class SitemapRequest(BaseModel):
    sitemap_url: str

semaphore = asyncio.Semaphore(CONCURRENCY)

async def fetch(url, client):
    async with semaphore:
        try:
            r = await client.get(url, timeout=TIMEOUT)
            return {
                "url": url,
                "status": r.status_code,
                "response_time": r.elapsed.total_seconds()
            }
        except Exception:
            return {
                "url": url,
                "status": "error",
                "response_time": None
            }

@app.post("/check-sitemap")
async def check_sitemap(data: SitemapRequest):
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(data.sitemap_url, timeout=TIMEOUT)
        except Exception:
            raise HTTPException(status_code=400, detail="Sitemap fetch failed")

        try:
            root = ET.fromstring(res.text)
            urls = [loc.text for loc in root.iter("{*}loc")]
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid XML")

        if len(urls) > MAX_URLS:
            urls = urls[:MAX_URLS]

        tasks = [fetch(url, client) for url in urls]
        results = await asyncio.gather(*tasks)

        errors = [r for r in results if r["status"] != 200]

        return {
            "total_urls": len(urls),
            "checked": len(results),
            "error_count": len(errors),
            "errors": errors
        }
