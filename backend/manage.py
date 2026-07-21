#!/usr/bin/env python
import os
import sys
import asyncio # 추가

# 윈도우 환경일 경우 Redis 타임아웃 버그를 막기 위한 호환성 코드 추가
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
