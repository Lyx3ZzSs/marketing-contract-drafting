import json
import sys

from app.storage import ObjectStorage

if __name__ == "__main__":
    try:
        result = ObjectStorage().smoke_test()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "message": "读写或清理失败，请检查测试 bucket 权限与连接",
                },
                ensure_ascii=False,
            )
        )
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False))
