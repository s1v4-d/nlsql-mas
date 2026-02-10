# Retail Insights Assistant - High Level Design (HLD)

## 1. Executive Summary

The Retail Insights Assistant is a GenAI-powered multi-agent system that enables natural language querying of large-scale retail sales data. The system translates user questions into SQL queries, executes them against a high-performance analytical data layer, and returns human-readable insights.

### Key Capabilities
- **Summarization Mode**: Generate automated business summaries from sales data
- **Conversational Q&A Mode**: Answer ad-hoc analytical questions in natural language
- **Scale**: Designed to handle 100GB+ of historical sales data efficiently

---

## 2. High-Level Architecture

![System Architecture](diagrams/01_system_architecture.png)

---

## 3. Component Details

### 3.1 User Interface Layer

| Component | Technology | Purpose |
|-----------|------------|---------|
| Web UI | Streamlit | Interactive chat interface for queries and summaries |
| Chat Interface | Streamlit Chat | Real-time conversational Q&A |
| Export | Pandas/Excel | Download query results and reports |

### 3.2 API Gateway Layer

| Component | Technology | Purpose |
|-----------|------------|---------|
| REST API | FastAPI | Query submission, history, health checks |
| WebSocket | FastAPI WebSocket | Real-time streaming responses |
| Auth | JWT/OAuth2 | User authentication and authorization |
| Validation | Pydantic | Request/response schema validation |

### 3.3 Agent Orchestration Layer

The core intelligence layer using **LangGraph** for multi-agent coordination:

| Agent | Responsibility | Technology |
|-------|---------------|------------|
| **Router Agent** | Intent classification (summarization vs Q&A vs chit-chat) | LangGraph + OpenAI |
| **SQL Generator Agent** | Natural language to SQL translation | LangGraph + OpenAI |
| **Validator Agent** | SQL syntax validation, schema conformance, safety checks | sqlglot + custom rules |
| **Executor Agent** | Execute SQL against DuckDB, format results | DuckDB connector |
| **Summarizer Agent** | Transform query results into human-readable narratives | LangGraph + OpenAI |

**Key Features:**
- **State Machine Control**: Conditional edges for retry loops
- **Checkpointing**: PostgresSaver for durable execution
- **Memory**: Thread-scoped conversation + cross-session knowledge store

### 3.4 Data Layer

| Component | Technology | Purpose |
|-----------|------------|---------|
| Query Engine | DuckDB | In-process OLAP for analytical queries |
| **Schema Registry** | Custom + PostgreSQL | Dynamic schema discovery and caching |
| Storage Format | Apache Parquet | Columnar storage with efficient compression |
| Object Storage | AWS S3 | Scalable data lake for historical data |
| Vector Index | pgvector | Semantic search for schema/examples |

**Schema Registry:**
- Auto-discovers tables from S3, local files, and PostgreSQL
- Caches schema metadata with configurable TTL (default: 5 minutes)
- Provides schema context to SQL Generator agent
- Supports multiple data sources simultaneously

**Optimization Strategies:**
- Hive-style partitioning (year/month/region)
- Parquet predicate pushdown
- Zone map filtering
- Column projection

### 3.5 Persistence Layer

| Component | Technology | Purpose |
|-----------|------------|---------|
| Primary DB | Aurora PostgreSQL | Metadata, checkpoints, vectors |
| Cache | Redis (ElastiCache) | Query results, session state |
| Vector Store | pgvector extension | Schema embeddings for RAG |

---

## 4. Data Flow

### 4.1 Query Processing Flow

```
User Query → FastAPI → Router Agent → [Intent: Q&A]
                            │
                            ▼
                    SQL Generator Agent
                            │
                            ▼
                    Validator Agent ─────┐
                            │            │
                            ▼            │ Invalid (max 3 retries)
                    [SQL Valid?]─────────┘
                            │
                            ▼ Valid
                    Executor Agent
                            │
                            ▼
                    DuckDB → S3 Parquet
                            │
                            ▼
                    Summarizer Agent
                            │
                            ▼
                    Response → User
```

### 4.2 Summarization Flow

```
User Request → FastAPI → Router Agent → [Intent: Summarize]
                                │
                                ▼
                        Executor Agent (predefined queries)
                                │
                                ▼
                        Summarizer Agent
                                │
                                ▼
                        Narrative Summary → User
```

---

## 5. Technology Stack

| Layer | Technology | Justification |
|-------|------------|---------------|
| **LLM Provider** | OpenAI GPT-4o | Best-in-class for SQL generation, model-agnostic design |
| **Agent Framework** | LangGraph | Production-ready, stateful multi-agent orchestration |
| **Data Layer** | DuckDB + Parquet | Zero-dependency OLAP, out-of-core processing |
| **API Framework** | FastAPI | High-performance async, Pydantic integration |
| **UI Framework** | Streamlit | Rapid prototyping, Python-native |
| **Vector Store** | pgvector | Co-located with PostgreSQL, no extra service |
| **Infrastructure** | AWS (ECS, Aurora, S3) | Scalable, managed services |
| **IaC** | Terraform | Reproducible infrastructure |
| **Dependency Mgmt** | uv + pyproject.toml | Fast, modern Python tooling |

---

## 6. Scalability Architecture

### 6.1 100GB+ Data Handling

```
┌─────────────────────────────────────────────────────────────────────┐
│                         S3 Data Lake                                 │
│  s3://bucket/sales/                                                 │
│  ├── year=2022/                                                     │
│  │   ├── month=01/                                                  │
│  │   │   ├── region=NORTH/*.parquet                                │
│  │   │   ├── region=SOUTH/*.parquet                                │
│  │   │   └── ...                                                   │
│  │   └── ...                                                       │
│  ├── year=2023/...                                                 │
│  └── year=2024/...                                                 │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    DuckDB Query Optimization                        │
│                                                                     │
│  Query: WHERE year=2023 AND month=6 AND region='NORTH'             │
│                                                                     │
│  ✅ Partition Pruning: Only reads s3://.../year=2023/month=06/...  │
│  ✅ Predicate Pushdown: Filters pushed to Parquet row groups       │
│  ✅ Column Projection: Only reads requested columns                │
│  ✅ Out-of-Core: Spills to disk if memory exceeded                 │
│                                                                     │
│  Result: 100GB → <1GB scanned → <5 second response                 │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 Horizontal Scaling

| Component | Scaling Strategy |
|-----------|------------------|
| FastAPI | ECS Fargate auto-scaling on CPU/connections |
| Agent Workers | Celery + Redis for async task distribution |
| DuckDB | Stateless per-request, scale with API instances |
| Aurora | Read replicas for query load distribution |
| S3 | Unlimited scale, pay-per-request |

---

## 7. Security Architecture

### 7.1 Data Security

- **Encryption at Rest**: S3 SSE-KMS, Aurora encryption
- **Encryption in Transit**: TLS 1.3 for all connections
- **Network Isolation**: VPC with private subnets for DB/storage

### 7.2 Application Security

- **LLM-Generated SQL**: Read-only database user, LIMIT enforcement
- **Input Validation**: Pydantic schemas at API boundary
- **SQL Validation**: sqlglot parsing, whitelist validation
- **Secrets Management**: AWS Secrets Manager with rotation

### 7.3 Access Control

- **API Authentication**: JWT tokens via Auth0/Cognito
- **Row-Level Security**: PostgreSQL RLS for multi-tenancy
- **Audit Logging**: CloudWatch logs for all queries

---

## 8. Deployment Architecture

### 8.1 AWS Infrastructure

```
┌─────────────────────────────────────────────────────────────────────┐
│                           AWS VPC                                    │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    Public Subnet                               │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │  │
│  │  │    ALB      │  │   NAT GW    │  │   Internet Gateway  │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    Private Subnet                              │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │                 ECS Fargate Cluster                     │  │  │
│  │  │  ┌─────────┐  ┌─────────────┐  ┌─────────────────────┐ │  │  │
│  │  │  │   API   │  │ Orchestrator│  │    Streamlit UI     │ │  │  │
│  │  │  │ Service │  │   Service   │  │      Service        │ │  │  │
│  │  │  └─────────┘  └─────────────┘  └─────────────────────┘ │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  │                                                                │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │  │
│  │  │   Aurora    │  │   Redis     │  │    S3 Endpoint      │   │  │
│  │  │  PostgreSQL │  │ ElastiCache │  │    (Gateway)        │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.2 Container Strategy

| Service | Container | Resources |
|---------|-----------|-----------|
| api | FastAPI + Uvicorn | 1 vCPU, 2GB RAM |
| orchestrator | LangGraph Worker | 2 vCPU, 4GB RAM |
| streamlit | Streamlit App | 0.5 vCPU, 1GB RAM |

---

## 9. Pros and Cons

### 9.1 Advantages

| Aspect | Benefit |
|--------|---------|
| **DuckDB + Parquet** | Zero infrastructure cost, query data in-place on S3 |
| **LangGraph** | Production-ready state machines, durable execution |
| **Multi-Agent** | Separation of concerns, testable components |
| **Model-Agnostic** | Abstract LLM interface, easy provider switching |
| **uv + pyproject.toml** | Modern, fast dependency management |
| **Terraform** | Reproducible infrastructure, GitOps ready |

### 9.2 Trade-offs

| Trade-off | Mitigation |
|-----------|------------|
| DuckDB single-node limitation | S3 partitioning, read replicas for extreme scale |
| LLM latency (~2-5s) | Streaming responses, query caching |
| LLM cost per query | Token optimization, caching frequent queries |
| Complexity of multi-agent | Comprehensive logging, observability |

---

## 10. Schema Registry & Dynamic Data Discovery

### 10.1 Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Data Sources                                  │
├──────────────────┬──────────────────┬───────────────────────────────┤
│   Local Files    │    S3 Bucket     │        PostgreSQL             │
│  data/*.parquet  │ s3://bucket/data │   information_schema          │
│  data/*.csv      │ s3://bucket/*.pq │   custom tables               │
└────────┬─────────┴────────┬─────────┴─────────────┬─────────────────┘
         │                  │                       │
         ▼                  ▼                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  Schema Registry (TTL: 5 min)                       │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ • Discovers tables, columns, types from all sources          │  │
│  │ • Caches schema metadata in memory + PostgreSQL              │  │
│  │ • Provides context to SQL Generator agent                    │  │
│  │ • Triggers refresh on new file detection or manual request   │  │
│  └───────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────┬────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      SQL Generator Agent                            │
│  Receives: table names, column names, types, sample values          │
└─────────────────────────────────────────────────────────────────────┘
```

### 10.2 Refresh Strategies

| Strategy | Trigger | Use Case |
|----------|---------|----------|
| **Startup Refresh** | App boot | Ensure schema is fresh on deploy |
| **TTL Cache** | Every N minutes | Balance freshness vs performance |
| **Manual Refresh** | Admin API call | Force refresh when data added |
| **S3 Event** | Lambda on upload | Real-time schema updates (future) |

### 10.3 New Data Handling

When new files are added to S3 or local storage:

1. **Automatic Discovery**: Schema Registry glob scans configured paths
2. **Schema Inference**: DuckDB `DESCRIBE` on new Parquet/CSV files
3. **Cache Update**: New tables added to in-memory cache
4. **Agent Context**: SQL Generator receives updated schema on next query

---

## 11. Extension Points

### 11.1 When to Extend

| Scenario | Extension |
|----------|-----------|
| **More Data Sources** | Add data extraction agents for APIs, databases |
| **Real-time Data** | Integrate Kafka/Kinesis for streaming ingestion |
| **Custom Visualizations** | Add Chart Generation Agent with Plotly |
| **Voice Interface** | Add Speech-to-Text preprocessing agent |
| **Multi-tenant SaaS** | Add tenant isolation at API and data layer |

### 10.2 Future Enhancements

1. **RAG for Unstructured Data**: Add vector search for product descriptions/documents
2. **Proactive Insights**: Scheduled analysis with anomaly detection
3. **Collaborative Features**: Share queries, dashboards between users
4. **Fine-tuned Models**: Custom SQL generation model on domain data

---

## 11. Cost Estimates

### 11.1 AWS Monthly Costs (Production)

| Service | Configuration | Est. Monthly Cost |
|---------|---------------|-------------------|
| ECS Fargate | 3 services, avg 2 tasks each | ~$200 |
| Aurora PostgreSQL | db.r6g.large, 100GB storage | ~$250 |
| ElastiCache Redis | cache.t3.medium | ~$50 |
| S3 | 100GB storage + requests | ~$10 |
| ALB | 1 load balancer | ~$25 |
| NAT Gateway | 1 AZ | ~$45 |
| **Total AWS** | | **~$580/month** |
| OpenAI API | ~10k queries/month @ $0.01/query | ~$100 |
| **Grand Total** | | **~$680/month** |

### 11.2 Cost Optimization Strategies

- Use Fargate Spot for dev/staging (40-70% savings)
- S3 Intelligent-Tiering for cold data
- Query caching to reduce LLM calls
- Reserved capacity for Aurora (30% savings)

---

## 12. Appendix

### 12.1 Technology Versions

| Technology | Version | Notes |
|------------|---------|-------|
| Python | 3.12 | Type hints, performance improvements |
| LangGraph | 1.0+ | Production-stable API |
| DuckDB | 1.0+ | S3 native support, parallel execution |
| FastAPI | 0.115+ | Latest async performance |
| Pydantic | 2.x | V2 with rust core |
| Terraform | 1.5+ | Module best practices |
| uv | 0.4+ | Fast package management |

### 12.2 References

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [DuckDB S3 Integration](https://duckdb.org/docs/guides/import/s3_import.html)
- [AWS Multi-Agent Architecture](https://docs.aws.amazon.com/prescriptive-guidance/latest/generative-ai-multi-agent-systems/)
- [PydanticAI Framework](https://ai.pydantic.dev/)
