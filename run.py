from sve_meta.web import create_app

if __name__ == "__main__":
    # create_app() 會在啟動時建表；
    # use_reloader=False 避免熱重載清空 /api/fetch 的記憶體快取（EVENTS_CACHE）
    create_app().run(debug=True, port=5000, use_reloader=False)
