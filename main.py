from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="Imweb AI Agent Server", description="A server for managing AI agents in Imweb", version="1.0.0")

@app.get("/")
async def root():
    return {"message": "Hello, Imweb AI Agent Server!"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/api/v1/status")
async def api_status():
    return {"api_version": "v1", "service": "imweb-ai-agent-server"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)