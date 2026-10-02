from fastapi import FastAPI

app = FastAPI(title="Library API")


@app.get("/health")
def health():
    return {"status": "ok"}
