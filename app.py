import os
import re
import json
import math
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse

import pandas as pd
import requests
import streamlit as st


API_URL = "https://api.dataforseo.com/v3/serp/google/maps/live/advanced"
USER_DATA_URL = "https://api.dataforseo.com/v3/appendix/user_data"
DB_PATH = Path(__file__).resolve().parent / "data" / "checks.sqlite3"
DEFAULT_LIVE_PRICE = 0.002
API_CHUNK_SIZE = 100
MAX_DOMAINS_PER_RUN = 5000
MAX_PARALLEL_REQUESTS = 5

GEO_LABELS = {
    "United Kingdom": "Великобритания — United Kingdom",
    "United States": "США — United States",
    "Canada": "Канада — Canada",
    "Australia": "Австралия — Australia",
    "New Zealand": "Новая Зеландия — New Zealand",
    "Ireland": "Ирландия — Ireland",
    "Germany": "Германия — Germany",
    "France": "Франция — France",
    "Spain": "Испания — Spain",
    "Italy": "Италия — Italy",
    "Portugal": "Португалия — Portugal",
    "Netherlands": "Нидерланды — Netherlands",
    "Belgium": "Бельгия — Belgium",
    "Luxembourg": "Люксембург — Luxembourg",
    "Switzerland": "Швейцария — Switzerland",
    "Austria": "Австрия — Austria",
    "Poland": "Польша — Poland",
    "Czechia": "Чехия — Czechia",
    "Slovakia": "Словакия — Slovakia",
    "Hungary": "Венгрия — Hungary",
    "Romania": "Румыния — Romania",
    "Bulgaria": "Болгария — Bulgaria",
    "Greece": "Греция — Greece",
    "Croatia": "Хорватия — Croatia",
    "Slovenia": "Словения — Slovenia",
    "Serbia": "Сербия — Serbia",
    "Bosnia and Herzegovina": "Босния и Герцеговина — Bosnia and Herzegovina",
    "Montenegro": "Черногория — Montenegro",
    "North Macedonia": "Северная Македония — North Macedonia",
    "Albania": "Албания — Albania",
    "Denmark": "Дания — Denmark",
    "Sweden": "Швеция — Sweden",
    "Norway": "Норвегия — Norway",
    "Finland": "Финляндия — Finland",
    "Iceland": "Исландия — Iceland",
    "Ukraine": "Украина — Ukraine",
    "Moldova": "Молдова — Moldova",
    "Lithuania": "Литва — Lithuania",
    "Latvia": "Латвия — Latvia",
    "Estonia": "Эстония — Estonia",
    "Turkey": "Турция — Turkey",
    "Georgia": "Грузия — Georgia",
    "Armenia": "Армения — Armenia",
    "Azerbaijan": "Азербайджан — Azerbaijan",
    "Israel": "Израиль — Israel",
    "United Arab Emirates": "ОАЭ — United Arab Emirates",
    "Saudi Arabia": "Саудовская Аравия — Saudi Arabia",
    "India": "Индия — India",
    "Pakistan": "Пакистан — Pakistan",
    "Bangladesh": "Бангладеш — Bangladesh",
    "Sri Lanka": "Шри-Ланка — Sri Lanka",
    "Japan": "Япония — Japan",
    "South Korea": "Южная Корея — South Korea",
    "Singapore": "Сингапур — Singapore",
    "Malaysia": "Малайзия — Malaysia",
    "Indonesia": "Индонезия — Indonesia",
    "Thailand": "Таиланд — Thailand",
    "Vietnam": "Вьетнам — Vietnam",
    "Philippines": "Филиппины — Philippines",
    "Mexico": "Мексика — Mexico",
    "Brazil": "Бразилия — Brazil",
    "Argentina": "Аргентина — Argentina",
    "Chile": "Чили — Chile",
    "Colombia": "Колумбия — Colombia",
    "Peru": "Перу — Peru",
    "South Africa": "ЮАР — South Africa",
    "Egypt": "Египет — Egypt",
    "Morocco": "Марокко — Morocco",
    "Nigeria": "Нигерия — Nigeria",
    "Kenya": "Кения — Kenya",
}

LANGUAGE_LABELS = {
    "en": "Английский — English (en)",
    "de": "Немецкий — German (de)",
    "fr": "Французский — French (fr)",
    "es": "Испанский — Spanish (es)",
    "it": "Итальянский — Italian (it)",
    "pt": "Португальский — Portuguese (pt)",
    "nl": "Нидерландский — Dutch (nl)",
    "pl": "Польский — Polish (pl)",
    "cs": "Чешский — Czech (cs)",
    "sk": "Словацкий — Slovak (sk)",
    "hu": "Венгерский — Hungarian (hu)",
    "ro": "Румынский — Romanian (ro)",
    "bg": "Болгарский — Bulgarian (bg)",
    "el": "Греческий — Greek (el)",
    "hr": "Хорватский — Croatian (hr)",
    "sl": "Словенский — Slovenian (sl)",
    "sr": "Сербский — Serbian (sr)",
    "da": "Датский — Danish (da)",
    "sv": "Шведский — Swedish (sv)",
    "no": "Норвежский — Norwegian (no)",
    "fi": "Финский — Finnish (fi)",
    "is": "Исландский — Icelandic (is)",
    "uk": "Украинский — Ukrainian (uk)",
    "ru": "Русский — Russian (ru)",
    "lt": "Литовский — Lithuanian (lt)",
    "lv": "Латышский — Latvian (lv)",
    "et": "Эстонский — Estonian (et)",
    "tr": "Турецкий — Turkish (tr)",
    "ka": "Грузинский — Georgian (ka)",
    "hy": "Армянский — Armenian (hy)",
    "az": "Азербайджанский — Azerbaijani (az)",
    "he": "Иврит — Hebrew (he)",
    "ar": "Арабский — Arabic (ar)",
    "hi": "Хинди — Hindi (hi)",
    "bn": "Бенгальский — Bengali (bn)",
    "ur": "Урду — Urdu (ur)",
    "ja": "Японский — Japanese (ja)",
    "ko": "Корейский — Korean (ko)",
    "ms": "Малайский — Malay (ms)",
    "id": "Индонезийский — Indonesian (id)",
    "th": "Тайский — Thai (th)",
    "vi": "Вьетнамский — Vietnamese (vi)",
    "tl": "Филиппинский — Filipino (tl)",
}


st.set_page_config(
    page_title="Google Maps Domain Search",
    page_icon="📍",
    layout="wide",
)


def get_secret(name: str) -> str:
    """Read a credential from Streamlit secrets or an environment variable."""
    try:
        value = st.secrets.get(name, "")
    except Exception:
        # Streamlit raises StreamlitSecretNotFoundError when no secrets file exists.
        value = ""
    return str(value or os.getenv(name, ""))


def normalize_domain(value: str) -> str:
    value = value.strip()
    if not value:
        return ""

    parsed = urlparse(value if "://" in value else f"https://{value}")
    domain = (parsed.hostname or value).lower().strip(".")
    return domain.removeprefix("www.")


def parse_domains(value: str) -> list[str]:
    """Parse newline-, comma-, semicolon-, or whitespace-separated domains."""
    domains = []
    seen = set()
    for part in re.split(r"[\s,;]+", value):
        domain = normalize_domain(part)
        if domain and domain not in seen:
            seen.add(domain)
            domains.append(domain)
    return domains


def api_cost(value: object) -> float:
    """Convert an API cost value to a safe floating-point number."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


@st.cache_data(ttl=60, show_spinner=False)
def fetch_account_data(login: str, password: str) -> dict:
    response = requests.get(USER_DATA_URL, auth=(login, password), timeout=30)
    response.raise_for_status()
    data = response.json()
    if data.get("status_code") and data["status_code"] != 20000:
        raise RuntimeError(data.get("status_message", "DataForSEO account API error"))

    tasks = data.get("tasks") or []
    results = tasks[0].get("result") or [] if tasks else []
    if not results:
        raise RuntimeError("DataForSEO не вернул данные аккаунта")

    account = results[0]
    balance = api_cost((account.get("money") or {}).get("balance"))
    try:
        live_price = api_cost(
            account["price"]["serp"]["live"]["advanced"]["priority_normal"][0]["cost"]
        )
    except (KeyError, IndexError, TypeError):
        live_price = DEFAULT_LIVE_PRICE

    return {
        "balance": balance,
        "live_price": live_price or DEFAULT_LIVE_PRICE,
    }


def database_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


def initialize_database() -> None:
    with database_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                location_name TEXT NOT NULL,
                language_code TEXT NOT NULL,
                depth INTEGER NOT NULL,
                search_this_area INTEGER NOT NULL,
                rows_json TEXT NOT NULL,
                raw_response_json TEXT NOT NULL,
                cost_usd REAL NOT NULL DEFAULT 0,
                checked_at TEXT NOT NULL,
                UNIQUE(domain, location_name, language_code, depth, search_this_area)
            )
            """
        )


def load_cached_checks(
    domains: list[str],
    location_name: str,
    language_code: str,
    depth: int,
    search_this_area: bool,
) -> dict[str, dict]:
    if not domains:
        return {}

    records = []
    with database_connection() as connection:
        # Keep each IN query below SQLite's variable limit.
        for start in range(0, len(domains), 500):
            domain_chunk = domains[start : start + 500]
            placeholders = ",".join("?" for _ in domain_chunk)
            query = f"""
                SELECT domain, rows_json, raw_response_json, cost_usd, checked_at
                FROM checks
                WHERE domain IN ({placeholders})
                  AND location_name = ?
                  AND language_code = ?
                  AND depth = ?
                  AND search_this_area = ?
            """
            parameters = [
                *domain_chunk,
                location_name,
                language_code,
                depth,
                int(search_this_area),
            ]
            records.extend(connection.execute(query, parameters).fetchall())

    return {
        record["domain"]: {
            "rows": json.loads(record["rows_json"]),
            "raw_response": json.loads(record["raw_response_json"]),
            "cost_usd": api_cost(record["cost_usd"]),
            "checked_at": record["checked_at"],
        }
        for record in records
    }


def save_check(
    domain: str,
    location_name: str,
    language_code: str,
    depth: int,
    search_this_area: bool,
    rows: list[dict],
    raw_response: dict,
    cost_usd: float,
) -> str:
    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with database_connection() as connection:
        connection.execute(
            """
            INSERT INTO checks (
                domain, location_name, language_code, depth, search_this_area,
                rows_json, raw_response_json, cost_usd, checked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(domain, location_name, language_code, depth, search_this_area)
            DO UPDATE SET
                rows_json = excluded.rows_json,
                raw_response_json = excluded.raw_response_json,
                cost_usd = excluded.cost_usd,
                checked_at = excluded.checked_at
            """,
            (
                domain,
                location_name,
                language_code,
                depth,
                int(search_this_area),
                json.dumps(rows, ensure_ascii=False),
                json.dumps(raw_response, ensure_ascii=False),
                cost_usd,
                checked_at,
            ),
        )
    return checked_at


def build_google_maps_url(item: dict) -> str:
    """Build a direct cross-platform Google Maps card URL."""
    title = str(item.get("title") or "")
    address = str(item.get("address") or "")
    latitude = item.get("latitude")
    longitude = item.get("longitude")

    query = ", ".join(part for part in (title, address) if part)
    if not query and latitude is not None and longitude is not None:
        query = f"{latitude},{longitude}"
    if not query:
        query = title or "Google Maps place"

    params = {"api": "1", "query": query}
    if item.get("place_id"):
        params["query_place_id"] = str(item["place_id"])
    return f"https://www.google.com/maps/search/?{urlencode(params)}"


def fetch_single_domain(
    login: str,
    password: str,
    domain: str,
    location_name: str,
    language_code: str,
    depth: int,
    search_this_area: bool,
) -> tuple[list[dict], dict, list[dict]]:
    payload = [
        {
            "keyword": domain,
            "location_name": location_name,
            "language_code": language_code,
            "depth": depth,
            "search_this_area": search_this_area,
        }
    ]

    response = requests.post(
        API_URL,
        auth=(login, password),
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("status_code") and data["status_code"] != 20000:
        raise RuntimeError(data.get("status_message", "DataForSEO API error"))

    rows = []
    task_errors = []
    for task in data.get("tasks") or []:
        task_data = task.get("data") or {}
        if isinstance(task_data, list):
            task_data = task_data[0] if task_data else {}
        query_domain = normalize_domain(str(task_data.get("keyword", "")))
        query_domain = query_domain or domain

        if task.get("status_code") and task["status_code"] != 20000:
            task_errors.append(
                {
                    "Domain": query_domain,
                    "Error": task.get("status_message", "DataForSEO task error"),
                }
            )
            continue

        for result in task.get("result") or []:
            result_domain = normalize_domain(str(result.get("keyword", "")))
            current_domain = result_domain or query_domain
            for item in result.get("items") or []:
                item_domain = normalize_domain(str(item.get("domain") or ""))
                website_domain = normalize_domain(str(item.get("url") or ""))
                if current_domain not in {item_domain, website_domain}:
                    continue

                rows.append(
                    {
                        "Результат": "✅ ДА",
                        "Проверяемый домен": current_domain,
                        "Название карточки": item.get("title"),
                        "Карточка Google Maps": build_google_maps_url(item),
                        "Сайт в карточке": item.get("url"),
                        "Rank": item.get("rank_absolute"),
                        "Rating": item.get("rating", {}).get("value")
                        if isinstance(item.get("rating"), dict)
                        else item.get("rating"),
                        "Reviews": item.get("rating", {}).get("votes_count")
                        if isinstance(item.get("rating"), dict)
                        else None,
                    }
                )

    if not rows and not task_errors:
        rows.append(
            {
                "Результат": "❌ НЕТ",
                "Проверяемый домен": domain,
                "Название карточки": None,
                "Карточка Google Maps": None,
                "Сайт в карточке": None,
                "Rank": None,
                "Rating": None,
                "Reviews": None,
            }
        )

    return rows, data, task_errors


def fetch_maps_results(
    login: str,
    password: str,
    domains: list[str],
    location_name: str,
    language_code: str,
    depth: int,
    search_this_area: bool,
    progress_callback=None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Run one Live API call per domain in bounded chunks."""
    request_args = {
        "login": login,
        "password": password,
        "location_name": location_name,
        "language_code": language_code,
        "depth": depth,
        "search_this_area": search_this_area,
    }
    all_rows = []
    raw_responses = []
    all_errors = []
    completed = 0
    total_chunks = math.ceil(len(domains) / API_CHUNK_SIZE)

    def report_progress(domain: str, chunk_number: int) -> None:
        nonlocal completed
        completed += 1
        if progress_callback:
            progress_callback(
                completed,
                len(domains),
                domain,
                chunk_number,
                total_chunks,
            )

    for chunk_index, chunk_start in enumerate(
        range(0, len(domains), API_CHUNK_SIZE), start=1
    ):
        domain_chunk = domains[chunk_start : chunk_start + API_CHUNK_SIZE]

        # Authenticate with the first request before launching parallel calls.
        if chunk_index == 1:
            first_domain = domain_chunk[0]
            rows, raw_data, task_errors = fetch_single_domain(
                domain=first_domain,
                **request_args,
            )
            all_rows.extend(rows)
            raw_responses.append({"domain": first_domain, "response": raw_data})
            all_errors.extend(task_errors)
            report_progress(first_domain, chunk_index)
            parallel_domains = domain_chunk[1:]
        else:
            parallel_domains = domain_chunk

        if not parallel_domains:
            continue

        with ThreadPoolExecutor(
            max_workers=min(MAX_PARALLEL_REQUESTS, len(parallel_domains))
        ) as executor:
            futures = {
                executor.submit(fetch_single_domain, domain=domain, **request_args): domain
                for domain in parallel_domains
            }
            for future in as_completed(futures):
                domain = futures[future]
                try:
                    rows, raw_data, task_errors = future.result()
                    all_rows.extend(rows)
                    raw_responses.append({"domain": domain, "response": raw_data})
                    all_errors.extend(task_errors)
                except requests.Timeout:
                    all_errors.append({"Domain": domain, "Error": "Timeout after 120 seconds"})
                except (requests.RequestException, ValueError, RuntimeError) as error:
                    all_errors.append({"Domain": domain, "Error": str(error)})
                finally:
                    report_progress(domain, chunk_index)

    domain_order = {domain: index for index, domain in enumerate(domains)}
    all_rows.sort(
        key=lambda row: domain_order.get(row.get("Проверяемый домен", ""), len(domains))
    )
    raw_responses.sort(key=lambda item: domain_order.get(item["domain"], len(domains)))
    return all_rows, raw_responses, all_errors


initialize_database()

st.title("📍 Google Maps Domain Search")
st.caption("Проверка: указана ли ссылка на домен в карточке Google Maps")

saved_login = get_secret("DATAFORSEO_LOGIN")
saved_password = get_secret("DATAFORSEO_PASSWORD")
account_balance = None
live_base_price = DEFAULT_LIVE_PRICE

with st.sidebar:
    st.header("Настройки API")
    if saved_login and saved_password:
        login = saved_login
        password = saved_password
        st.success("Данные DataForSEO загружены из Secrets.")
        st.caption("Credentials остаются на сервере и не передаются в браузер.")
    else:
        login = st.text_input(
            "DataForSEO login",
            placeholder="login@example.com",
        )
        password = st.text_input("DataForSEO password", type="password")
        st.caption("Для деплоя сохраните данные в Streamlit Secrets — не в GitHub.")

    if login and password:
        if st.button("Обновить баланс", use_container_width=True):
            fetch_account_data.clear()
        try:
            account_data = fetch_account_data(login, password)
            account_balance = account_data["balance"]
            live_base_price = account_data["live_price"]
            st.metric("Баланс DataForSEO", f"${account_balance:.4f}")
            st.caption(f"Базовая ставка Live Advanced: ${live_base_price:.6f}")
        except (requests.RequestException, ValueError, RuntimeError) as error:
            st.warning(f"Не удалось получить баланс: {error}")

with st.container(border=True):
    domain_input = st.text_area(
        "Домены",
        value="bucknallbowlingclub.co.uk",
        placeholder="example.com\nanother-site.co.uk",
        help="По одному домену на строку или через запятую/точку с запятой. Каждый домен — отдельный платный Live-запрос.",
        height=160,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        location_name = st.selectbox(
            "Локация",
            options=list(GEO_LABELS),
            index=list(GEO_LABELS).index("United Kingdom"),
            format_func=GEO_LABELS.get,
            help="Начните печатать название страны на русском или английском.",
        )
    with col2:
        language_code = st.selectbox(
            "Язык выдачи",
            options=list(LANGUAGE_LABELS),
            index=list(LANGUAGE_LABELS).index("en"),
            format_func=LANGUAGE_LABELS.get,
            help="Начните печатать название языка или его код.",
        )
    with col3:
        depth = st.number_input("Глубина", min_value=1, max_value=700, value=20)

    search_this_area = st.checkbox("Искать только в указанной области", value=False)
    refresh_cached = st.checkbox(
        "Обновить сохранённые результаты через API",
        value=False,
        help="Если выключено, повторные проверки с теми же параметрами берутся из базы бесплатно.",
    )
    preview_domains = parse_domains(domain_input)
    preview_cached = load_cached_checks(
        domains=preview_domains,
        location_name=location_name,
        language_code=language_code,
        depth=int(depth),
        search_this_area=search_this_area,
    )
    preview_api_count = (
        len(preview_domains)
        if refresh_cached
        else len([domain for domain in preview_domains if domain not in preview_cached])
    )
    depth_multiplier = max(1, math.ceil(int(depth) / 100))
    estimated_cost = preview_api_count * live_base_price * depth_multiplier

    estimate_col1, estimate_col2, estimate_col3 = st.columns(3)
    estimate_col1.metric("Уникальных доменов", len(preview_domains))
    estimate_col2.metric("Будет API-запросов", preview_api_count)
    estimate_col3.metric("Предварительная стоимость", f"до ${estimated_cost:.6f}")
    st.caption(
        f"Из базы: {len(preview_domains) - preview_api_count} · "
        f"Ставка: ${live_base_price:.6f} за каждые 100 результатов на домен. "
        "Предварительный расчёт не списывает деньги."
    )
    if account_balance is not None:
        balance_after = account_balance - estimated_cost
        if balance_after < 0:
            st.error(
                f"Недостаточно средств: баланс ${account_balance:.4f}, "
                f"оценка до ${estimated_cost:.6f}."
            )
        else:
            st.caption(f"Ожидаемый остаток после проверки: ${balance_after:.4f}")

    submitted = st.button("Найти", type="primary", use_container_width=True)

if submitted:
    domains = parse_domains(domain_input)
    normalized_location = location_name.strip()
    normalized_language = language_code.strip().lower()
    selected_depth = int(depth)

    if not domains:
        st.error("Укажите хотя бы один домен.")
    elif len(domains) > MAX_DOMAINS_PER_RUN:
        st.error(
            f"Указано доменов: {len(domains)}. За один запуск можно обработать "
            f"максимум {MAX_DOMAINS_PER_RUN}."
        )
    elif not normalized_location or not normalized_language:
        st.error("Укажите локацию и код языка.")
    else:
        try:
            cached_checks = load_cached_checks(
                domains=domains,
                location_name=normalized_location,
                language_code=normalized_language,
                depth=selected_depth,
                search_this_area=search_this_area,
            )
            api_domains = domains if refresh_cached else [
                domain for domain in domains if domain not in cached_checks
            ]

            rows = []
            raw_data = []
            task_errors = []
            cost_rows = []
            cached_domains_used = set()

            if not refresh_cached:
                for domain in domains:
                    cached = cached_checks.get(domain)
                    if not cached:
                        continue
                    cached_domains_used.add(domain)
                    for stored_row in cached["rows"]:
                        row = dict(stored_row)
                        row["Источник"] = "🗄️ База данных"
                        row["Проверено (UTC)"] = cached["checked_at"]
                        rows.append(row)
                    cost_rows.append(
                        {
                            "Домен": domain,
                            "Источник": "База данных",
                            "Стоимость текущего запуска, USD": 0.0,
                            "Стоимость сохранённой проверки, USD": cached["cost_usd"],
                        }
                    )

            fresh_rows = []
            if api_domains:
                if not login or not password:
                    st.error(
                        "Для доменов, которых нет в базе, укажите DataForSEO login и password."
                    )
                    task_errors.extend(
                        {"Domain": domain, "Error": "Нет данных API для новой проверки"}
                        for domain in api_domains
                    )
                else:
                    progress_bar = st.progress(
                        0,
                        text=f"Подготовка {len(api_domains)} API-проверок…",
                    )

                    def update_progress(
                        completed: int,
                        total: int,
                        current_domain: str,
                        chunk_number: int,
                        total_chunks: int,
                    ) -> None:
                        progress_bar.progress(
                            min(completed / total, 1.0),
                            text=(
                                f"Пакет {chunk_number}/{total_chunks} · "
                                f"Проверено {completed}/{total} · {current_domain}"
                            ),
                        )

                    with st.spinner(
                        f"В базе найдено: {len(cached_checks)} · Запросов к API: {len(api_domains)}…"
                    ):
                        fresh_rows, raw_data, api_errors = fetch_maps_results(
                            login=login,
                            password=password,
                            domains=api_domains,
                            location_name=normalized_location,
                            language_code=normalized_language,
                            depth=selected_depth,
                            search_this_area=search_this_area,
                            progress_callback=update_progress,
                        )
                    progress_bar.progress(
                        1.0,
                        text=f"API-проверка завершена: {len(api_domains)}/{len(api_domains)}",
                    )
                    task_errors.extend(api_errors)

            fresh_rows_by_domain = {
                domain: [
                    row for row in fresh_rows if row["Проверяемый домен"] == domain
                ]
                for domain in api_domains
            }
            error_domains = {
                normalize_domain(str(error.get("Domain") or "")) for error in task_errors
            }

            for response_item in raw_data:
                domain = response_item["domain"]
                domain_rows = fresh_rows_by_domain.get(domain) or []
                cost = api_cost(response_item["response"].get("cost"))
                checked_at = None

                if domain_rows and domain not in error_domains:
                    checked_at = save_check(
                        domain=domain,
                        location_name=normalized_location,
                        language_code=normalized_language,
                        depth=selected_depth,
                        search_this_area=search_this_area,
                        rows=domain_rows,
                        raw_response=response_item["response"],
                        cost_usd=cost,
                    )
                    source = "🔄 API (обновлено)" if domain in cached_checks else "🌐 API"
                    for stored_row in domain_rows:
                        row = dict(stored_row)
                        row["Источник"] = source
                        row["Проверено (UTC)"] = checked_at
                        rows.append(row)

                cost_rows.append(
                    {
                        "Домен": domain,
                        "Источник": "API",
                        "Стоимость текущего запуска, USD": cost,
                        "Стоимость сохранённой проверки, USD": cost,
                    }
                )

            # If forced refresh failed, preserve and show the last valid database result.
            if refresh_cached:
                refreshed_domains = {
                    row["Проверяемый домен"]
                    for row in rows
                    if row.get("Источник") == "🔄 API (обновлено)"
                }
                for domain in domains:
                    cached = cached_checks.get(domain)
                    if not cached or domain in refreshed_domains:
                        continue
                    cached_domains_used.add(domain)
                    for stored_row in cached["rows"]:
                        row = dict(stored_row)
                        row["Источник"] = "🗄️ База — обновление не удалось"
                        row["Проверено (UTC)"] = cached["checked_at"]
                        rows.append(row)

            domain_order = {domain: index for index, domain in enumerate(domains)}
            rows.sort(
                key=lambda row: domain_order.get(
                    row.get("Проверяемый домен", ""), len(domains)
                )
            )
            total_cost = sum(
                item["Стоимость текущего запуска, USD"] for item in cost_rows
            )

            if not rows:
                st.warning("Не удалось получить результаты проверки.")
            else:
                dataframe = pd.DataFrame(rows)
                found_domains = dataframe.loc[
                    dataframe["Результат"] == "✅ ДА", "Проверяемый домен"
                ].nunique()
                not_found_domains = dataframe.loc[
                    dataframe["Результат"] == "❌ НЕТ", "Проверяемый домен"
                ].nunique()
                st.success(
                    f"Домен найден в карточке: {found_domains} · Домен не найден: {not_found_domains}"
                )
                metric1, metric2, metric3, metric4 = st.columns(4)
                metric1.metric("Доменов в запросе", len(domains))
                metric2.metric("Получено из базы", len(cached_domains_used))
                metric3.metric("API-запросов", len(raw_data))
                metric4.metric("Стоимость запуска", f"${total_cost:.6f}")
                st.caption(
                    f"«НЕТ» означает: среди первых {selected_depth} результатов Google Maps "
                    "не найдено карточки, где домен сайта точно совпадает с введённым."
                )
                st.dataframe(
                    dataframe,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Карточка Google Maps": st.column_config.LinkColumn(
                            "Карточка Google Maps", display_text="Открыть карточку"
                        ),
                        "Сайт в карточке": st.column_config.LinkColumn("Сайт в карточке"),
                        "Rating": st.column_config.NumberColumn("Rating", format="%.1f"),
                        "Источник": st.column_config.TextColumn("Источник"),
                    },
                )
                st.download_button(
                    "Скачать CSV",
                    data=dataframe.to_csv(index=False).encode("utf-8-sig"),
                    file_name="google_maps_domain_check.csv",
                    mime="text/csv",
                )

            if cost_rows:
                with st.expander("Расчёт стоимости"):
                    st.caption(
                        "Данные из базы не создают новых расходов. Стоимость API взята "
                        "из поля cost ответа DataForSEO."
                    )
                    st.dataframe(
                        pd.DataFrame(cost_rows),
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Стоимость текущего запуска, USD": st.column_config.NumberColumn(
                                "Стоимость текущего запуска, USD", format="$%.6f"
                            ),
                            "Стоимость сохранённой проверки, USD": st.column_config.NumberColumn(
                                "Стоимость сохранённой проверки, USD", format="$%.6f"
                            )
                        },
                    )
                    st.markdown(f"**Стоимость текущего запуска: ${total_cost:.6f}**")

            if task_errors:
                st.warning(f"Ошибок по отдельным доменам: {len(task_errors)}")
                with st.expander("Показать ошибки"):
                    st.dataframe(pd.DataFrame(task_errors), use_container_width=True, hide_index=True)

            if raw_data:
                with st.expander("Новые ответы API (JSON)"):
                    if len(raw_data) > 20:
                        st.info(
                            f"Для быстрого отображения показаны первые 20 из {len(raw_data)} "
                            "ответов. Полный JSON доступен для скачивания."
                        )
                    st.json(raw_data[:20])
                    st.download_button(
                        "Скачать полный JSON",
                        data=json.dumps(raw_data, ensure_ascii=False, indent=2).encode("utf-8"),
                        file_name="dataforseo_responses.json",
                        mime="application/json",
                    )
        except requests.Timeout:
            st.error("DataForSEO не ответил за 120 секунд. Попробуйте ещё раз.")
        except requests.HTTPError as error:
            status = error.response.status_code if error.response is not None else "unknown"
            st.error(f"HTTP-ошибка DataForSEO: {status}")
        except (requests.RequestException, ValueError, RuntimeError) as error:
            st.error(f"Ошибка DataForSEO: {error}")
