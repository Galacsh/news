"""Google Gemini API client using official google-genai SDK with structured JSON enforcement, exponential backoff, and mock mode."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from google import genai
from google.genai import errors, types

logger = logging.getLogger(__name__)


# ============================================================================
# Exceptions
# ============================================================================

class GeminiAPIError(Exception):
    """Exception raised for Gemini API communication, rate-limit, or response parsing errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_body = response_body

    def __str__(self) -> str:
        if self.status_code is not None:
            return f"[{self.status_code}] {self.message}"
        return self.message


# ============================================================================
# Gemini Client
# ============================================================================

class GeminiClient:
    """Google Gemini client powered by official google-genai SDK."""

    DEFAULT_MODEL: str = "gemini-3.5-flash"
    DEFAULT_TIMEOUT: float = 90.0
    DEFAULT_MAX_RETRIES: int = 3
    DEFAULT_BASE_BACKOFF: float = 2.0

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_backoff: float = DEFAULT_BASE_BACKOFF,
        dry_run: bool = False,
        mock_mode: bool = False,
    ) -> None:
        self.model = model or os.environ.get("GEMINI_MODEL", self.DEFAULT_MODEL)
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.dry_run = dry_run

        resolved_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")
        self.api_key = resolved_key.strip()

        # Mock mode if explicitly requested or MOCK key used
        self.mock_mode = mock_mode or self.dry_run or (self.api_key.upper().startswith("MOCK"))

        if not self.mock_mode and not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY must be provided via argument or environment variable, "
                "or enable dry_run=True / mock_mode=True."
            )

        self._genai_client: genai.Client | None = None
        if not self.mock_mode:
            http_options = types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    attempts=self.max_retries,
                    initial_delay=self.base_backoff,
                    http_status_codes=[408, 429, 500, 502, 503, 504],
                ),
                timeout=int(self.timeout * 1000),  # ms
            )
            self._genai_client = genai.Client(api_key=self.api_key, http_options=http_options)

    def is_mock(self) -> bool:
        """Check if client operates in mock/dry-run mode."""
        return self.mock_mode

    def generate_json(
        self,
        contents: str | None = None,
        system_instruction: str | None = None,
        response_schema: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate structured JSON response adhering to response_schema.

        Supports both positional and keyword argument patterns:
          - generate_json(contents, system_instruction, response_schema)
          - generate_json(prompt=..., schema=...)
        """
        prompt = contents or kwargs.get("prompt") or ""
        schema = response_schema or kwargs.get("schema")

        if self.is_mock():
            return self._generate_mock_response(schema)

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            system_instruction=system_instruction,
        )

        last_error: Exception | None = None
        backoff = self.base_backoff

        for attempt in range(1, self.max_retries + 1):
            try:
                assert self._genai_client is not None
                response = self._genai_client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                raw_text = response.text if response and response.text else ""
                if not raw_text.strip():
                    raise GeminiAPIError("Empty response text from Gemini API")
                return json.loads(raw_text)

            except errors.APIError as e:
                code = getattr(e, "code", 500)
                is_retryable = code in (429, 503, 504)
                last_error = GeminiAPIError(
                    message=f"Gemini API error ({code}): {e.message if hasattr(e, 'message') else str(e)}",
                    status_code=code,
                )
                if not is_retryable or attempt == self.max_retries:
                    raise last_error

                logger.warning(
                    "Gemini API returned status %d on attempt %d/%d. Retrying in %.2fs...",
                    code,
                    attempt,
                    self.max_retries,
                    backoff,
                )
                time.sleep(backoff)
                backoff *= 2

            except (json.JSONDecodeError, ValueError) as e:
                raise GeminiAPIError(f"Failed to parse Gemini model response as JSON: {e}") from e

            except Exception as e:
                if isinstance(e, GeminiAPIError):
                    raise
                last_error = GeminiAPIError(f"Network or unexpected error calling Gemini API: {e}")
                if attempt == self.max_retries:
                    raise last_error
                logger.warning(
                    "Network error calling Gemini API on attempt %d/%d: %s. Retrying in %.2fs...",
                    attempt,
                    self.max_retries,
                    e,
                    backoff,
                )
                time.sleep(backoff)
                backoff *= 2

        raise last_error or GeminiAPIError("Exceeded maximum retries for Gemini API")

    def _generate_mock_response(self, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a valid structured response dictionary matching schema without network calls."""
        return {
            "topHeadlines": [
                {
                    "id": 1,
                    "categoryId": 1,
                    "headline": "[모의] 주요 민생 및 경제 안정 법안 여야 전격 합의",
                    "summary": "여야 원내 지도부가 임시국회 본회의를 앞두고 주요 민생 법안 처리에 전격 합의했습니다.",
                    "impact": "민생 경기 회복을 위한 입법 불확실성이 해소되며 정책 추진력이 강화될 전망입니다.",
                    "links": [
                        {
                            "title": "국회 민생 법안 합의 처리 타결",
                            "url": "https://news.example.com/pol/headline-01",
                        }
                    ],
                },
                {
                    "id": 2,
                    "categoryId": 2,
                    "headline": "[모의] 한국은행 금융통화위원회 기준금리 연 3.50% 동결 결정",
                    "summary": "한국은행이 소비자물가 안정세와 가계대출 추이를 면밀히 모니터링하며 기준금리를 현행 유지했습니다.",
                    "impact": "금융시장 유동성 관리와 더불어 부동산 및 대출금리 변동성을 완화하는 기조가 유지됩니다.",
                    "links": [
                        {
                            "title": "한은 금통위 기준금리 동결 결정문",
                            "url": "https://news.example.com/econ/headline-02",
                        }
                    ],
                },
                {
                    "id": 3,
                    "categoryId": 6,
                    "headline": "[모의] 국내 빅테크 차세대 온디바이스 생성형 AI 모델 상용화",
                    "summary": "국내 주요 테크 기업들이 스마트폰과 로봇에 탑재 가능한 초경량 초거대 AI 모델을 정식 출시했습니다.",
                    "impact": "글로벌 테크 기업과의 기술 격차를 축소하고 지능형 서비스 생태계 주도권을 확보할 것으로 기대됩니다.",
                    "links": [
                        {
                            "title": "차세대 온디바이스 AI 상용화 발표",
                            "url": "https://news.example.com/tech/headline-03",
                        }
                    ],
                },
            ],
            "articles": [
                {
                    "id": 4,
                    "categoryId": 1,
                    "headline": "[모의 브리핑] 국회 예산결산특별위원회 종합 질의 진행",
                    "summary": "국회 예결위가 정부 제출 예산안의 적정성을 평가하고 민생 예산 확충 방안을 심도 있게 논의했습니다.",
                    "impact": "국가 재정 건전성 확보와 복지 지출 확충 간의 균형 잡힌 재정 운용이 기대됩니다.",
                    "links": [
                        {
                            "title": "예결위 예산안 심사 소식",
                            "url": "https://news.example.com/pol/article-01",
                        }
                    ],
                },
                {
                    "id": 5,
                    "categoryId": 2,
                    "headline": "[모의 브리핑] 반도체 중심 수출 호조로 무역수지 연속 흑자",
                    "summary": "고대역폭메모리(HBM)와 첨단 부품 수출 호조세로 무역수지가 연속 흑자를 기록했습니다.",
                    "impact": "국내 제조업 경기 반등과 함께 외환시장 안정 및 경제 성장률 제고에 기여하고 있습니다.",
                    "links": [
                        {
                            "title": "관세청 월간 수출입 동향 집계",
                            "url": "https://news.example.com/econ/article-02",
                        }
                    ],
                },
                {
                    "id": 6,
                    "categoryId": 6,
                    "headline": "[모의 브리핑] 초거대 AI 데이터센터 친환경 냉각 기술 도입",
                    "summary": "빅테크 기업들이 전력 효율을 극대화하기 위해 액체 침전 냉각 방식의 차세대 데이터센터를 구축하고 있습니다.",
                    "impact": "AI 인프라 확장 과정에서 발생하는 전력 소비와 탄소 배출을 획기적으로 절감할 전망입니다.",
                    "links": [
                        {
                            "title": "AI 데이터센터 친환경 인프라 분석",
                            "url": "https://news.example.com/tech/article-03",
                        }
                    ],
                },
            ],
        }
