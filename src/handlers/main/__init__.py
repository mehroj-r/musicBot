from .upload import router as upload_router

def setup_main_handlers(dp):
    dp.include_router(upload_router)