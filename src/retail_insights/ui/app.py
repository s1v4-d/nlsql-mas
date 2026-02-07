"""Streamlit UI for Retail Insights Assistant.

A conversational interface for natural language queries on retail data.
"""

import os
from typing import Any

import streamlit as st

# Page configuration
st.set_page_config(
    page_title="Retail Insights Assistant",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# API URL from environment (for Docker networking)
API_URL = os.getenv("API_URL", "http://localhost:8000")


def init_session_state() -> None:
    """Initialize session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        import uuid

        st.session_state.session_id = str(uuid.uuid4())


def render_sidebar() -> None:
    """Render the sidebar with settings and info."""
    with st.sidebar:
        st.title("🛒 Retail Insights")
        st.markdown("---")

        st.markdown("### About")
        st.markdown(
            """
            Ask questions about your retail sales data in plain English.

            **Examples:**
            - What were the top 5 categories by revenue?
            - Show me sales trends for Maharashtra
            - Which products had the highest returns?
            """
        )

        st.markdown("---")

        # Settings
        st.markdown("### Settings")
        max_results = st.slider(
            "Max Results",
            min_value=10,
            max_value=500,
            value=100,
            step=10,
            help="Maximum number of rows to return",
        )
        st.session_state.max_results = max_results

        # Clear chat button
        if st.button("Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

        st.markdown("---")
        st.caption(f"Session: {st.session_state.session_id[:8]}...")


def render_chat_message(role: str, content: str, data: Any = None) -> None:
    """Render a chat message."""
    with st.chat_message(role):
        st.markdown(content)
        if data is not None:
            st.dataframe(data, use_container_width=True)


def query_api(question: str) -> dict[str, Any]:
    """Send query to the API.

    TODO: Implement when API routes are ready.
    This is a placeholder that returns mock data.
    """
    # Mock response for now - will be replaced with actual API call
    return {
        "success": True,
        "sql": "SELECT * FROM sales LIMIT 10",
        "summary": f"Here's what I found for: {question}",
        "data": None,
        "message": "API integration pending - this is a placeholder response.",
    }


def render_main_chat() -> None:
    """Render the main chat interface."""
    st.title("💬 Ask Your Data")

    # Display chat history
    for message in st.session_state.messages:
        render_chat_message(
            role=message["role"],
            content=message["content"],
            data=message.get("data"),
        )

    # Chat input
    if prompt := st.chat_input("Ask a question about your retail data..."):
        # Add user message
        st.session_state.messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )
        render_chat_message("user", prompt)

        # Get response from API
        with st.spinner("Analyzing..."):
            response = query_api(prompt)

        # Add assistant message
        assistant_content = response.get("summary", response.get("message", ""))
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": assistant_content,
                "data": response.get("data"),
            }
        )
        render_chat_message("assistant", assistant_content, response.get("data"))


def main() -> None:
    """Main application entry point."""
    init_session_state()
    render_sidebar()
    render_main_chat()


if __name__ == "__main__":
    main()
