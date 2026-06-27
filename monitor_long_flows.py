"""
监控长时间运行的 Flow 任务，超过 1 小时自动取消。
每 10 分钟检查一次，Ctrl+C 退出。

用法:
    python monitor_long_flows.py              # 正常运行，超时自动取消
    python monitor_long_flows.py --dry-run    # 只检查不取消
    python monitor_long_flows.py --timeout 2  # 超时阈值改为 2 小时
"""
import sys
import time
import logging
import tableauserverclient as tsc
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))
DEFAULT_TIMEOUT_HOURS = 1
CHECK_INTERVAL = 600  # 秒


def to_cst(dt):
    if not dt:
        return ''
    return dt.astimezone(CST).strftime('%Y-%m-%d %H:%M:%S')


def connect():
    load_dotenv()
    server_url = os.getenv('TABLEAU_SERVER_URL')
    token_name = os.getenv('PERSONAL_ACCESS_TOKEN_NAME')
    token_secret = os.getenv('PERSONAL_ACCESS_TOKEN_SECRET')
    site_name = os.getenv('SITE_NAME', '')
    tableau_auth = tsc.PersonalAccessTokenAuth(token_name, token_secret, site_name)
    server = tsc.Server(server_url, use_server_version=False)
    server.version = '3.21'
    return server, tableau_auth


def get_flow_names(server):
    """批量获取 flow ID -> 名称 映射"""
    flow_map = {}
    flows, _ = server.flows.get()
    for flow in flows:
        flow_map[flow.id] = flow.name
    return flow_map


def check_and_cancel(timeout_hours, dry_run):
    server, tableau_auth = connect()
    with server.auth.sign_in(tableau_auth):
        now_cst = datetime.now(CST)
        since = now_cst - timedelta(hours=24)
        since_utc = since.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        req = tsc.RequestOptions()
        req.filter.add(tsc.Filter(tsc.RequestOptions.Field.StartedAt,
                                  tsc.RequestOptions.Operator.GreaterThanOrEqual,
                                  since_utc))
        runs = server.flow_runs.get(req)

        # 收集未完成的 runs
        pending = []
        for r in runs:
            if not r.completed_at and r.started_at:
                elapsed = datetime.now(timezone.utc) - r.started_at.replace(tzinfo=timezone.utc)
                if elapsed >= timedelta(hours=timeout_hours):
                    pending.append((r, int(elapsed.total_seconds() / 60)))

        if not pending:
            log.info("本轮检查完成，无超时任务。")
            return

        # 获取 flow 名称
        flow_map = get_flow_names(server)

        cancelled = []
        for r, elapsed_min in pending:
            flow_name = flow_map.get(r.flow_id, r.flow_id)
            mode = "[DRY-RUN] " if dry_run else ""
            log.warning(
                f"{mode}超时! {flow_name} | RunID={r.id} | "
                f"已运行 {elapsed_min} 分钟 | 开始={to_cst(r.started_at)} | "
                f"JobID={r.background_job_id}"
            )
            if not dry_run:
                try:
                    server.jobs.cancel(r.background_job_id)
                    log.info(f"  -> 已取消 RunID={r.id}")
                    cancelled.append(r)
                except Exception as e:
                    log.error(f"  -> 取消失败 RunID={r.id}: {e}")
            else:
                cancelled.append(r)

        if dry_run:
            log.info(f"[DRY-RUN] 本轮共 {len(cancelled)} 个超时任务（未实际取消）。")
        else:
            log.warning(f"本轮共取消 {len(cancelled)} 个任务。")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='监控长时间运行的 Flow 任务')
    parser.add_argument('--dry-run', action='store_true', help='只检查不取消')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT_HOURS,
                        help=f'超时阈值（小时），默认 {DEFAULT_TIMEOUT_HOURS}')
    parser.add_argument('--once', action='store_true', help='只检查一次就退出')
    args = parser.parse_args()

    mode = "DRY-RUN" if args.dry_run else "LIVE"
    log.info(f"启动监控: 模式={mode}, 超时阈值={args.timeout}h, 检查间隔={CHECK_INTERVAL}s")

    if args.once:
        check_and_cancel(args.timeout, args.dry_run)
        return

    while True:
        try:
            check_and_cancel(args.timeout, args.dry_run)
        except KeyboardInterrupt:
            log.info("用户中断，退出。")
            break
        except Exception as e:
            log.error(f"检查异常: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    main()
