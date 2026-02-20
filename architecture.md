---
title: Rick and Morty API — High-Level Architecture
---
flowchart TB
    %% ── External ──────────────────────────────────────────────────────────
    Client(["👤 Client\n(curl / browser / app)"])
    RaMAPI(["🌐 Rick & Morty\nPublic API\nrickandmortyapi.com"])

    %% ── Runtime config ────────────────────────────────────────────────────
    subgraph CFG ["⚙️ Runtime Config (mounted files)"]
        direction LR
        SecretsFile["secrets.json\n(host / user / pass / dbname)"]
        ConfigFile["config.yaml\n(log_level)"]
    end

    %% ── Application ───────────────────────────────────────────────────────
    subgraph APP ["🐍 FastAPI Application  (main.py · Uvicorn · port 8000)"]
        direction TB

        ArgParse["argparse\n--config / --secret"]
        Logger["JSON Logger\n(JsonFormatter → stdout)"]
        RateLimiter["Rate Limiter\npyrate-limiter · fastapi-limiter\n50 req / sec per endpoint"]

        subgraph ENDPOINTS ["API Endpoints"]
            direction LR
            SyncEP["POST /sync\nsync_data()"]
            DataEP["GET  /data\nget_data()"]
            MonEP["GET  /db-mon\nmonitoring()"]
        end

        RgetHelper["rget()\nHTTP helper\n(requests · timeout 5/30 s)"]
        Lifespan["Lifespan Manager\nasyncpg connection pool\n(startup / shutdown)"]
    end

    %% ── Data layer ────────────────────────────────────────────────────────
    subgraph DB ["🐘 PostgreSQL"]
        direction TB
        PGMain[("postgres\n(default DB)")]
        AppDB[("rickandmorty DB\nauto-created on startup")]
        CharTable[["character table\nid SERIAL PK\ndata JSONB"]]
        AppDB --> CharTable
    end

    %% ── CI/CD ─────────────────────────────────────────────────────────────
    subgraph CICD ["🔄 GitHub Actions CI/CD"]
        direction LR
        LintJob["lint-and-security\nRuff · mypy · Bandit · pip-audit"]
        UnitJob["unit-tests\npytest · coverage"]
        BuildJob["build-and-test\nDocker build · Trivy scan\nintegration tests"]
        PushJob["push-image\nDocker Hub\nmulti-arch amd64/arm64"]
        LintJob --> UnitJob --> BuildJob --> PushJob
    end

    Registry(["🐳 Docker Hub\nrickandmorty-api:latest"])

    %% ── Connections ───────────────────────────────────────────────────────

    %% config boot
    CFG          -->|"read at startup"| ArgParse
    ArgParse     --> Logger
    ArgParse     --> Lifespan

    %% client → app
    Client       -->|"HTTP request"| RateLimiter
    RateLimiter  --> ENDPOINTS

    %% sync flow
    SyncEP       -->|"calls"| RgetHelper
    RgetHelper   -->|"GET /api/{resource}?species=Human\n&status=alive&origin=Earth\n(paginated)"| RaMAPI
    RaMAPI       -->|"JSON pages"| RgetHelper
    RgetHelper   -->|"results"| SyncEP
    SyncEP       -->|"INSERT … ON CONFLICT DO NOTHING"| CharTable

    %% data flow
    DataEP       -->|"SELECT … ORDER BY"| CharTable
    CharTable    -->|"rows"| DataEP

    %% monitoring flow
    MonEP        -->|"SELECT 1 / COUNT(*)"| AppDB

    %% pool
    Lifespan     -->|"create_pool()\nCREATE DATABASE if missing"| PGMain
    PGMain       --- AppDB

    %% logging
    ENDPOINTS    -.->|"log events"| Logger
    RgetHelper   -.->|"log events"| Logger
    Lifespan     -.->|"log events"| Logger

    %% responses
    ENDPOINTS    -->|"JSONResponse"| Client

    %% CI/CD
    BuildJob     -->|"image scan"| Registry
    PushJob      -->|"push"| Registry

    %% ── Styles ────────────────────────────────────────────────────────────
    classDef external  fill:#dbeafe,stroke:#2563eb,color:#1e3a5f
    classDef app       fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef db        fill:#fef9c3,stroke:#ca8a04,color:#713f12
    classDef cicd      fill:#f3e8ff,stroke:#9333ea,color:#3b0764
    classDef config    fill:#ffedd5,stroke:#ea580c,color:#7c2d12

    class Client,RaMAPI,Registry external
    class ArgParse,Logger,RateLimiter,SyncEP,DataEP,MonEP,RgetHelper,Lifespan app
    class PGMain,AppDB,CharTable db
    class LintJob,UnitJob,BuildJob,PushJob cicd
    class SecretsFile,ConfigFile config