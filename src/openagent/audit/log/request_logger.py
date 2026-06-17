"""RequestLogger 门面 — 仿照 fh-ai app/commons/log/requestLogger.

每请求发 2 条: ``start`` (``delay=-1``) + ``end`` (有 ``delay`` / ``result`` /
``errorMessage``). 只能由 :class:`LogMiddleware` 内部调用.

字段:
- ``requestTime``   请求开始时间
- ``reqSeqNo``      流水号
- ``serviceName``   路由路径
- ``instanceId``    实例标识
- ``ip``            客户端 IP (X-Forwarded-For 优先, 否则 ``request.ip``)
- ``delay``         响应时间 (毫秒), start 时 ``-1``
- ``result``        ``SUCC`` / ``ERROR``
- ``errorMessage``  status_code + 业务错误码 + 错误信息
- ``mainReqSeqNo``  跨服务主链 (请求头 ``main_request_seq_no``)
- ``bizNo``         业务流水号 (请求头 ``bizNo``)
- ``logId``         平台 logId
"""
from __future__ import annotations

from datetime import datetime

from openagent.audit.log.dto import RequestLog
from openagent.audit.log.object_log_writer import ObjectLogWriter
from openagent.audit.log.seq_no import get_date_seq_no, get_instance_id


class RequestLogger:
    def __init__(self, log_system_type: str) -> None:
        self._type_prefix = f"REQUEST_LOG_{log_system_type.upper()}"

    @property
    def type_prefix(self) -> str:
        return self._type_prefix

    def write_start(
        self,
        req_seq_no: str,
        service_name: str,
        ip: str,
        *,
        main_req_seq_no: str = "",
        biz_no: str = "",
    ) -> None:
        self._emit(
            req_seq_no=req_seq_no,
            service_name=service_name,
            ip=ip,
            delay_ms=-1,
            result="SUCC",
            error_message="",
            main_req_seq_no=main_req_seq_no,
            biz_no=biz_no,
        )

    def write_end(
        self,
        req_seq_no: str,
        service_name: str,
        ip: str,
        *,
        delay_ms: int,
        result: str,
        error_message: str = "",
        main_req_seq_no: str = "",
        biz_no: str = "",
    ) -> None:
        self._emit(
            req_seq_no=req_seq_no,
            service_name=service_name,
            ip=ip,
            delay_ms=delay_ms,
            result=result,
            error_message=error_message,
            main_req_seq_no=main_req_seq_no,
            biz_no=biz_no,
        )

    def _emit(
        self,
        *,
        req_seq_no: str,
        service_name: str,
        ip: str,
        delay_ms: int,
        result: str,
        error_message: str,
        main_req_seq_no: str,
        biz_no: str,
    ) -> None:
        writer = ObjectLogWriter.get_instance()
        if writer is None:
            return
        log = RequestLog(
            type=self._type_prefix,
            requestTime=datetime.now(),
            reqSeqNo=req_seq_no,
            serviceName=service_name,
            instanceId=get_instance_id(),
            ip=ip,
            delay=delay_ms,
            result=result,
            errorMessage=error_message,
            mainReqSeqNo=main_req_seq_no,
            bizNo=biz_no,
            logId=get_date_seq_no("LOG_ID"),
        )
        writer.write_request(log)


_request_logger: RequestLogger | None = None


def get_request_logger() -> RequestLogger | None:
    return _request_logger


def init_request_logger(log_system_type: str) -> RequestLogger:
    global _request_logger
    _request_logger = RequestLogger(log_system_type)
    return _request_logger
