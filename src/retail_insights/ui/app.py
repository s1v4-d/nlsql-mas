"""Streamlit UI for Retail Insights Assistant."""

import io
import os
import uuid
from datetime import datetime
from typing import Any

import httpx
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Retail Insights Assistant",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

API_URL = os.getenv("API_URL", "http://localhost:8000")
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "120"))


def init_session_state() -> None:
    if "initialized" not in st.session_state:
        st.session_state.initialized = True
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.max_results = 100
        st.session_state.query_mode = "query"
        st.session_state.last_results = None
        st.session_state.api_healthy = True
        st.session_state.api_key = ""
        st.session_state.authenticated = False
        st.session_state.auth_error = ""
        st.session_state.auth_scope = ""


def check_api_health() -> bool:
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{API_URL}/health")
            return response.status_code == 200
    except Exception:
        return False


def validate_api_key(api_key: str) -> tuple[bool, str]:
    """Validate API key by making a test request to the auth endpoint."""
    if not api_key:
        return False, "API key cannot be empty"
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                f"{API_URL}/auth/validate",
                headers={"X-API-Key": api_key},
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("valid"):
                    scope = data.get("scope", "user")
                    return True, scope
                return False, "Invalid API key"
            elif response.status_code == 401:
                return False, "Invalid API key"
            elif response.status_code == 403:
                return False, "Access denied"
            else:
                return False, f"Authentication failed (HTTP {response.status_code})"
    except httpx.ConnectError:
        return False, "Cannot connect to API server"
    except Exception as e:
        return False, f"Validation failed: {e!s}"


def query_api(question: str, mode: str = "query") -> dict[str, Any]:
    if not st.session_state.authenticated:
        return {
            "success": False,
            "error_type": "auth",
            "message": "Please authenticate first. Enter your API key in the sidebar and click Authenticate.",
        }
    try:
        with httpx.Client(timeout=API_TIMEOUT) as client:
            response = client.post(
                f"{API_URL}/api/v1/query",
                json={
                    "question": question,
                    "mode": mode,
                    "session_id": st.session_state.session_id,
                    "max_results": st.session_state.max_results,
                },
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": st.session_state.api_key,
                },
            )
            response.raise_for_status()
            return response.json()

    except httpx.ConnectError:
        return {
            "success": False,
            "error_type": "connection",
            "message": "Cannot connect to API server. Please check if the service is running.",
        }
    except httpx.TimeoutException:
        return {
            "success": False,
            "error_type": "timeout",
            "message": "Request timed out. Try a simpler query or add filters.",
        }
    except httpx.HTTPStatusError as e:
        error_detail = "Unknown error"
        try:
            error_detail = e.response.json().get("message", e.response.json().get("detail", str(e)))
        except Exception:
            error_detail = str(e)
        return {
            "success": False,
            "error_type": "http",
            "message": f"API error: {error_detail}",
            "status_code": e.response.status_code,
        }
    except Exception as e:
        return {
            "success": False,
            "error_type": "unknown",
            "message": f"Unexpected error: {e!s}",
        }


def summarize_api(
    time_period: str = "last_quarter",
    region: str | None = None,
    category: str | None = None,
    include_trends: bool = True,
) -> dict[str, Any]:
    if not st.session_state.authenticated:
        return {
            "success": False,
            "error_type": "auth",
            "message": "Please authenticate first. Enter your API key in the sidebar and click Authenticate.",
        }
    try:
        with httpx.Client(timeout=API_TIMEOUT) as client:
            response = client.post(
                f"{API_URL}/api/v1/summarize",
                json={
                    "time_period": time_period,
                    "region": region,
                    "category": category,
                    "include_trends": include_trends,
                },
                headers={
                    "Content-Type": "application/json",
                    "X-Session-ID": st.session_state.session_id,
                    "X-API-Key": st.session_state.api_key,
                },
            )
            response.raise_for_status()
            return response.json()

    except Exception as e:
        return {
            "success": False,
            "error_type": "unknown",
            "message": f"Summary failed: {e!s}",
        }


def display_error(response: dict[str, Any]) -> None:
    error_type = response.get("error_type", "unknown")
    message = response.get("message", "An error occurred")

    if error_type == "connection":
        st.error(message)
        st.info("Make sure the API server is running: `uv run uvicorn retail_insights.api.app:app`")
    elif error_type == "timeout":
        st.error(message)
        st.info("Try adding date filters or limiting your query scope.")
    elif error_type == "auth":
        st.error(message)
        st.info("Enter your API key in the sidebar under 'Authentication'.")
    elif error_type == "http":
        status = response.get("status_code", "")
        st.error(f"HTTP {status}: {message}")
        if status == 401:
            st.info("Check your API key in the sidebar.")
    else:
        st.error(message)


def add_export_buttons(
    df: pd.DataFrame, prefix: str = "retail_data", key_suffix: str | None = None
) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}"
    unique_key = key_suffix or str(id(df))

    col1, col2 = st.columns(2)

    with col1:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"{filename}.csv",
            mime="text/csv",
            key=f"csv_{unique_key}",
        )

    with col2:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Results")
        st.download_button(
            label="Download Excel",
            data=buffer.getvalue(),
            file_name=f"{filename}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"excel_{unique_key}",
        )


def render_sidebar() -> None:
    with st.sidebar:
        st.title("Retail Insights")

        api_status = check_api_health()
        st.session_state.api_healthy = api_status
        if api_status:
            st.success("API Connected")
        else:
            st.error("API Offline")

        st.markdown("---")

        st.markdown("### Authentication")
        if st.session_state.authenticated:
            scope_label = (
                st.session_state.auth_scope.upper() if st.session_state.auth_scope else "USER"
            )
            st.success(f"Authenticated ({scope_label})")
            if st.button("Logout", use_container_width=True):
                st.session_state.api_key = ""
                st.session_state.authenticated = False
                st.session_state.auth_error = ""
                st.session_state.auth_scope = ""
                st.rerun()
        else:
            api_key_input = st.text_input(
                "API Key",
                value="",
                type="password",
                placeholder="Enter your API key",
                help="Required for API access",
                key="api_key_input",
            )
            if st.button("Authenticate", use_container_width=True, type="primary"):
                if api_key_input:
                    valid, scope_or_error = validate_api_key(api_key_input)
                    if valid:
                        st.session_state.api_key = api_key_input
                        st.session_state.authenticated = True
                        st.session_state.auth_error = ""
                        st.session_state.auth_scope = scope_or_error
                        st.rerun()
                    else:
                        st.session_state.auth_error = scope_or_error
                else:
                    st.session_state.auth_error = "Please enter an API key"
            if st.session_state.auth_error:
                st.error(st.session_state.auth_error)
            else:
                st.warning("API key required")

        st.markdown("---")

        st.markdown("### Query Mode")
        mode = st.radio(
            "Select mode",
            options=["query", "summarize"],
            format_func=lambda x: "Q&A" if x == "query" else "Summary",
            horizontal=True,
            label_visibility="collapsed",
        )
        st.session_state.query_mode = mode

        if mode == "query":
            st.caption("Ask natural language questions about your data")
        else:
            st.caption("Generate automated sales summaries")

        st.markdown("---")

        st.markdown("### Settings")
        max_results = st.slider(
            "Max Results",
            min_value=10,
            max_value=500,
            value=st.session_state.max_results,
            step=10,
            help="Maximum number of rows to return",
        )
        st.session_state.max_results = max_results

        st.markdown("---")

        st.markdown("### Example Questions")
        examples = [
            "What were the top 5 categories by revenue?",
            "Show sales trends for Maharashtra",
            "Which products had the highest returns?",
            "Compare Q1 vs Q2 performance",
        ]
        for example in examples:
            if st.button(example, key=f"ex_{example[:20]}", use_container_width=True):
                st.session_state.pending_query = example
                st.rerun()

        st.markdown("---")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Clear", use_container_width=True):
                st.session_state.messages = []
                st.session_state.last_results = None
                st.rerun()
        with col2:
            if st.button("New Session", use_container_width=True):
                st.session_state.session_id = str(uuid.uuid4())
                st.session_state.messages = []
                st.session_state.last_results = None
                st.rerun()

        st.markdown("---")
        st.caption(f"Session: `{st.session_state.session_id[:8]}...`")


def render_chat_message(
    role: str,
    content: str,
    data: list[dict[str, Any]] | None = None,
    sql: str | None = None,
    execution_time: float | None = None,
    msg_index: int = 0,
) -> None:
    with st.chat_message(role):
        st.markdown(content)

        if sql:
            with st.expander("View SQL Query"):
                st.code(sql, language="sql")

        if data is not None and len(data) > 0:
            df = pd.DataFrame(data)
            st.session_state.last_results = df

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
            )

            add_export_buttons(df, key_suffix=f"msg_{msg_index}")

        if execution_time:
            st.caption(f"{execution_time:.0f}ms")


def render_main_chat() -> None:
    st.title("Ask Your Data")

    if not st.session_state.api_healthy:
        st.warning(
            "API server is not reachable. Start it with: "
            "`uv run uvicorn retail_insights.api.app:app --reload`"
        )

    pending = st.session_state.get("pending_query")
    if pending:
        st.session_state.messages.append({"role": "user", "content": pending})
        del st.session_state.pending_query

    for idx, message in enumerate(st.session_state.messages):
        render_chat_message(
            role=message["role"],
            content=message["content"],
            data=message.get("data"),
            sql=message.get("sql"),
            execution_time=message.get("execution_time"),
            msg_index=idx,
        )

    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        last_msg = st.session_state.messages[-1]
        if "processed" not in last_msg:
            question = last_msg["content"]

            with st.chat_message("assistant"):
                with st.status("Processing...", expanded=True) as status:
                    st.write("Analyzing question...")

                    if st.session_state.query_mode == "query":
                        st.write("Generating SQL...")
                        response = query_api(question, "query")
                    else:
                        st.write("Generating summary...")
                        response = query_api(question, "summarize")

                    if response.get("success"):
                        status.update(label="Complete!", state="complete", expanded=False)
                    else:
                        status.update(label="Error", state="error", expanded=False)

                if response.get("success"):
                    answer = response.get("answer", response.get("summary", ""))
                    sql = response.get("sql_query")
                    data = response.get("data")
                    exec_time = response.get("execution_time_ms")

                    st.markdown(answer)

                    if sql:
                        with st.expander("View SQL Query"):
                            st.code(sql, language="sql")

                    if data:
                        df = pd.DataFrame(data)
                        st.session_state.last_results = df
                        st.dataframe(df, use_container_width=True, hide_index=True)
                        add_export_buttons(df, key_suffix="live")

                    if exec_time:
                        st.caption(f"{exec_time:.0f}ms")

                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": answer,
                            "data": data,
                            "sql": sql,
                            "execution_time": exec_time,
                        }
                    )
                else:
                    display_error(response)
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": f"Error: {response.get('message', 'Query failed')}",
                        }
                    )

            last_msg["processed"] = True

    if prompt := st.chat_input("Ask a question about your retail data..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()


def main() -> None:
    init_session_state()
    render_sidebar()
    render_main_chat()


if __name__ == "__main__":
    main()
