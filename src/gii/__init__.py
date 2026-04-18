"""Global Interconnectedness Index — composite bilateral scores across trade, travel, and geopolitics."""


def main():
    import uvicorn
    uvicorn.run("gii.api.app:app", host="0.0.0.0", port=8000, reload=True)
