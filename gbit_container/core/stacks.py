'''
Stack templates for gbit-container v2.0.0 — Process Engine
All stacks use start_cmd/runtime instead of Docker images.
'''

from typing import Dict, Any, Optional, List


# ── Stack Templates ─────────────────────────────────────────────
# Each stack defines services with:
#   - start_cmd: command to start the service (list or string)
#   - build_cmd: command to install dependencies
#   - runtime: language/runtime type (node, python, go, rust, java, dotnet, php, ruby)
#   - port: primary host port
#   - environment: env vars
#   - depends_on: service dependencies
#   - healthcheck: port-based probe config

STACKS: Dict[str, Dict[str, Any]] = {



        "gbit-db": {
        "name": "GBit DB",
        "description": "GBit Database com Next.js + Database Engine + Portal AI",
        "tags": ["gbit", "database", "next.js", "node", "ai"],
        "services": {

            "app": {
                "runtime": "node",
                "start_cmd": "npm run dev",
                "build_cmd": "npm install",
                "build": ".",
                "port": 3000,
                "depends_on": ["database"],
                "environment": {
                    "NODE_ENV": "development",
                    "PORT": "3000"
                },
                "healthcheck": {
                    "port": 3000,
                    "timeout": 30
                }
            },

            "database": {
                "runtime": "node",
                "start_cmd": "node server.js",
                "build_cmd": "npm install",
                "build": "./gbit-database",
                "port": 4200,
                "environment": {
                    "NODE_ENV": "development",
                    "PORT": "4200"
                },
                "healthcheck": {
                    "port": 4200,
                    "timeout": 30
                }
            },

            "portal": {
                "runtime": "node",
                "start_cmd": "npm run portal",
                "build_cmd": "npm install",
                "build": ".",
                "port": 4100,
                "depends_on": ["database"],
                "environment": {
                    "NODE_ENV": "development"
                },
                "healthcheck": {
                    "port": 4100,
                    "timeout": 30
                }
            }
        }
    },

    "node-fullstack": {
        "name": "Node Fullstack",
        "description": "Aplicacao fullstack Next.js + API Express + MongoDB",
        "tags": ["node", "next.js", "express", "mongodb"],
        "services": {
            "app": {
                "runtime": "node",
                "start_cmd": "npm run dev",
                "build_cmd": "npm install",
                "build": ".",
                "port": 3000,
                "environment": {
                    "NODE_ENV": "development",
                    "PORT": "3000",
                    "API_URL": "http://localhost:4000",
                },
                "healthcheck": {"port": 3000, "timeout": 30},
            },
            "api": {
                "runtime": "node",
                "start_cmd": "node server.js",
                "build_cmd": "npm install",
                "build": "./api",
                "port": 4000,
                "depends_on": ["db"],
                "environment": {
                    "NODE_ENV": "development",
                    "PORT": "4000",
                    "DB_HOST": "127.0.0.1",
                    "DB_PORT": "27017",
                },
                "healthcheck": {"port": 4000, "timeout": 20},
            },
            "db": {
                "runtime": "mongodb",
                "start_cmd": "mongod --dbpath .gbit/data/db --port 27017",
                "port": 27017,
                "environment": {},
                "healthcheck": {"port": 27017, "timeout": 15},
            },
        },
    },

    "fastapi-backend": {
        "name": "FastAPI Backend",
        "description": "API Python com FastAPI + Uvicorn + PostgreSQL",
        "tags": ["python", "fastapi", "postgresql"],
        "services": {
            "api": {
                "runtime": "python",
                "start_cmd": "uvicorn main:app --host 0.0.0.0 --port 8000 --reload",
                "build_cmd": "pip install -r requirements.txt",
                "build": ".",
                "port": 8000,
                "depends_on": ["db"],
                "environment": {
                    "DATABASE_URL": "postgresql://postgres:postgres@127.0.0.1:5432/appdb",
                    "PORT": "8000",
                },
                "healthcheck": {"port": 8000, "timeout": 20},
            },
            "db": {
                "runtime": "postgresql",
                "start_cmd": "postgres -D .gbit/data/db -p 5432",
                "port": 5432,
                "environment": {
                    "PGDATA": ".gbit/data/db",
                },
                "healthcheck": {"port": 5432, "timeout": 15},
            },
        },
    },

    "go-microservices": {
        "name": "Go Microservices",
        "description": "Microservicos Go com gRPC + REST + Redis",
        "tags": ["go", "grpc", "redis", "microservices"],
        "services": {
            "gateway": {
                "runtime": "go",
                "start_cmd": "go run ./cmd/gateway",
                "build_cmd": "go mod download",
                "build": ".",
                "port": 8080,
                "depends_on": ["usersvc", "cache"],
                "environment": {
                    "PORT": "8080",
                    "USERSVC_ADDR": "127.0.0.1:9090",
                    "REDIS_ADDR": "127.0.0.1:6379",
                },
                "healthcheck": {"port": 8080, "timeout": 20},
            },
            "usersvc": {
                "runtime": "go",
                "start_cmd": "go run ./cmd/users",
                "build": ".",
                "port": 9090,
                "environment": {
                    "PORT": "9090",
                },
                "healthcheck": {"port": 9090, "timeout": 20},
            },
            "cache": {
                "runtime": "redis",
                "start_cmd": "redis-server --port 6379 --dir .gbit/data/cache",
                "port": 6379,
                "healthcheck": {"port": 6379, "timeout": 10},
            },
        },
    },

    "spring-backend": {
        "name": "Spring Backend",
        "description": "API Java Spring Boot + PostgreSQL + Redis",
        "tags": ["java", "spring", "postgresql", "redis"],
        "services": {
            "app": {
                "runtime": "java",
                "start_cmd": "mvn spring-boot:run",
                "build_cmd": "mvn compile",
                "build": ".",
                "port": 8080,
                "depends_on": ["db", "cache"],
                "environment": {
                    "SERVER_PORT": "8080",
                    "SPRING_DATASOURCE_URL": "jdbc:postgresql://127.0.0.1:5432/appdb",
                    "SPRING_REDIS_HOST": "127.0.0.1",
                },
                "healthcheck": {"port": 8080, "timeout": 40},
            },
            "db": {
                "runtime": "postgresql",
                "start_cmd": "postgres -D .gbit/data/db -p 5432",
                "port": 5432,
                "environment": {},
                "healthcheck": {"port": 5432, "timeout": 15},
            },
            "cache": {
                "runtime": "redis",
                "start_cmd": "redis-server --port 6379 --dir .gbit/data/cache",
                "port": 6379,
                "healthcheck": {"port": 6379, "timeout": 10},
            },
        },
    },

    "rust-backend": {
        "name": "Rust Backend",
        "description": "API Rust Axum + PostgreSQL",
        "tags": ["rust", "axum", "postgresql"],
        "services": {
            "api": {
                "runtime": "rust",
                "start_cmd": "cargo run",
                "build_cmd": "cargo build",
                "build": ".",
                "port": 8080,
                "depends_on": ["db"],
                "environment": {
                    "DATABASE_URL": "postgresql://postgres:postgres@127.0.0.1:5432/appdb",
                    "HOST": "0.0.0.0",
                    "PORT": "8080",
                },
                "healthcheck": {"port": 8080, "timeout": 40},
            },
            "db": {
                "runtime": "postgresql",
                "start_cmd": "postgres -D .gbit/data/db -p 5432",
                "port": 5432,
                "healthcheck": {"port": 5432, "timeout": 15},
            },
        },
    },

    "laravel-fullstack": {
        "name": "Laravel Fullstack",
        "description": "App PHP Laravel + Vue.js + MySQL",
        "tags": ["php", "laravel", "vue", "mysql"],
        "services": {
            "app": {
                "runtime": "php",
                "start_cmd": "php artisan serve --host=0.0.0.0 --port=8000",
                "build_cmd": "composer install",
                "build": ".",
                "port": 8000,
                "depends_on": ["db"],
                "environment": {
                    "APP_ENV": "local",
                    "DB_HOST": "127.0.0.1",
                    "DB_PORT": "3306",
                    "DB_DATABASE": "appdb",
                },
                "healthcheck": {"port": 8000, "timeout": 20},
            },
            "frontend": {
                "runtime": "node",
                "start_cmd": "npm run dev",
                "build_cmd": "npm install",
                "build": "./frontend",
                "port": 3000,
                "environment": {
                    "PORT": "3000",
                    "API_URL": "http://localhost:8000",
                },
                "healthcheck": {"port": 3000, "timeout": 20},
            },
            "db": {
                "runtime": "mysql",
                "start_cmd": "mysqld --datadir=.gbit/data/db --port=3306",
                "port": 3306,
                "healthcheck": {"port": 3306, "timeout": 15},
            },
        },
    },

    "rails-fullstack": {
        "name": "Rails Fullstack",
        "description": "App Ruby on Rails + PostgreSQL + Redis",
        "tags": ["ruby", "rails", "postgresql", "redis"],
        "services": {
            "app": {
                "runtime": "ruby",
                "start_cmd": "bundle exec rails server -b 0.0.0.0 -p 3000",
                "build_cmd": "bundle install",
                "build": ".",
                "port": 3000,
                "depends_on": ["db", "cache"],
                "environment": {
                    "DATABASE_URL": "postgresql://localhost:5432/appdb",
                    "REDIS_URL": "redis://127.0.0.1:6379",
                    "PORT": "3000",
                },
                "healthcheck": {"port": 3000, "timeout": 25},
            },
            "db": {
                "runtime": "postgresql",
                "start_cmd": "postgres -D .gbit/data/db -p 5432",
                "port": 5432,
                "healthcheck": {"port": 5432, "timeout": 15},
            },
            "cache": {
                "runtime": "redis",
                "start_cmd": "redis-server --port 6379 --dir .gbit/data/cache",
                "port": 6379,
                "healthcheck": {"port": 6379, "timeout": 10},
            },
        },
    },

    "dotnet-backend": {
        "name": ".NET Backend",
        "description": "API .NET 8 + SQL Server + Redis",
        "tags": ["dotnet", "c#", "sqlserver", "redis"],
        "services": {
            "api": {
                "runtime": "dotnet",
                "start_cmd": "dotnet run",
                "build_cmd": "dotnet build",
                "build": ".",
                "port": 8080,
                "depends_on": ["db", "cache"],
                "environment": {
                    "ASPNETCORE_ENVIRONMENT": "Development",
                    "ASPNETCORE_URLS": "http://0.0.0.0:8080",
                    "ConnectionStrings__DefaultConnection": "Server=127.0.0.1,1433;Database=appdb;User=sa;Password=Passw0rd;",
                },
                "healthcheck": {"port": 8080, "timeout": 25},
            },
            "db": {
                "runtime": "mssql",
                "start_cmd": "sqlservr",
                "port": 1433,
                "environment": {
                    "ACCEPT_EULA": "Y",
                    "SA_PASSWORD": "Passw0rd",
                },
                "healthcheck": {"port": 1433, "timeout": 30},
            },
            "cache": {
                "runtime": "redis",
                "start_cmd": "redis-server --port 6379 --dir .gbit/data/cache",
                "port": 6379,
                "healthcheck": {"port": 6379, "timeout": 10},
            },
        },
    },

    "minimal": {
        "name": "Minimal",
        "description": "Servico unico com Node.js — ideal para prototipos rapidos",
        "tags": ["node", "minimal", "quickstart"],
        "services": {
            "app": {
                "runtime": "node",
                "start_cmd": "npm start",
                "build_cmd": "npm install",
                "build": ".",
                "port": 3000,
                "environment": {
                    "NODE_ENV": "development",
                    "PORT": "3000",
                },
                "healthcheck": {"port": 3000, "timeout": 15},
            },
        },
    },

    "mongo-express": {
        "name": "Mongo + Express",
        "description": "MongoDB com painel Express para visualizacao de dados",
        "tags": ["mongodb", "express", "admin"],
        "services": {
            "mongo": {
                "runtime": "mongodb",
                "start_cmd": "mongod --dbpath .gbit/data/mongo --port 27017",
                "port": 27017,
                "environment": {},
                "healthcheck": {"port": 27017, "timeout": 15},
            },
            "express": {
                "runtime": "node",
                "start_cmd": "node app.js",
                "build_cmd": "npm install",
                "build": ".",
                "port": 8081,
                "depends_on": ["mongo"],
                "environment": {
                    "ME_CONFIG_MONGODB_URL": "mongodb://127.0.0.1:27017",
                    "PORT": "8081",
                },
                "healthcheck": {"port": 8081, "timeout": 20},
            },
        },
    },

    "postgres-pgadmin": {
        "name": "PostgreSQL + pgAdmin",
        "description": "PostgreSQL com pgAdmin para gerenciamento visual",
        "tags": ["postgresql", "pgadmin", "admin"],
        "services": {
            "postgres": {
                "runtime": "postgresql",
                "start_cmd": "postgres -D .gbit/data/postgres -p 5432",
                "port": 5432,
                "environment": {
                    "POSTGRES_USER": "postgres",
                    "POSTGRES_PASSWORD": "postgres",
                },
                "healthcheck": {"port": 5432, "timeout": 15},
            },
            "pgadmin": {
                "runtime": "python",
                "start_cmd": "python manage.py runserver 0.0.0.0:5050",
                "build_cmd": "pip install -r requirements.txt",
                "build": ".",
                "port": 5050,
                "depends_on": ["postgres"],
                "environment": {
                    "PGADMIN_DEFAULT_EMAIL": "admin@admin.com",
                    "PGADMIN_DEFAULT_PASSWORD": "admin",
                    "PORT": "5050",
                },
                "healthcheck": {"port": 5050, "timeout": 25},
            },
        },
    },

    "redis-insight": {
        "name": "Redis + Insight",
        "description": "Redis com RedisInsight para monitoramento visual",
        "tags": ["redis", "insight", "monitoring"],
        "services": {
            "redis": {
                "runtime": "redis",
                "start_cmd": "redis-server --port 6379 --dir .gbit/data/redis",
                "port": 6379,
                "healthcheck": {"port": 6379, "timeout": 10},
            },
            "insight": {
                "runtime": "node",
                "start_cmd": "npm start",
                "build_cmd": "npm install",
                "build": ".",
                "port": 8001,
                "depends_on": ["redis"],
                "environment": {
                    "REDIS_HOST": "127.0.0.1",
                    "REDIS_PORT": "6379",
                    "PORT": "8001",
                },
                "healthcheck": {"port": 8001, "timeout": 20},
            },
        },
    },

    "mysql-phpmyadmin": {
        "name": "MySQL + phpMyAdmin",
        "description": "MySQL com phpMyAdmin para gerenciamento de banco",
        "tags": ["mysql", "phpmyadmin", "admin"],
        "services": {
            "mysql": {
                "runtime": "mysql",
                "start_cmd": "mysqld --datadir=.gbit/data/mysql --port=3306",
                "port": 3306,
                "environment": {
                    "MYSQL_ROOT_PASSWORD": "root",
                    "MYSQL_DATABASE": "appdb",
                },
                "healthcheck": {"port": 3306, "timeout": 15},
            },
            "phpmyadmin": {
                "runtime": "php",
                "start_cmd": "php -S 0.0.0.0:8080",
                "build_cmd": "composer install",
                "build": ".",
                "port": 8080,
                "depends_on": ["mysql"],
                "environment": {
                    "PMA_HOST": "127.0.0.1",
                    "PMA_PORT": "3306",
                },
                "healthcheck": {"port": 8080, "timeout": 20},
            },
        },
    },

    "nats-streaming": {
        "name": "NATS Streaming",
        "description": "NATS Server com Streaming para mensageria leve",
        "tags": ["nats", "streaming", "messaging"],
        "services": {
            "nats": {
                "runtime": "nats",
                "start_cmd": "nats-server --port 4222 --store_dir .gbit/data/nats --sd",
                "port": 4222,
                "environment": {},
                "healthcheck": {"port": 4222, "timeout": 10},
            },
            "monitor": {
                "runtime": "node",
                "start_cmd": "npm start",
                "build_cmd": "npm install",
                "build": ".",
                "port": 8222,
                "depends_on": ["nats"],
                "environment": {
                    "NATS_URL": "nats://127.0.0.1:4222",
                    "PORT": "8222",
                },
                "healthcheck": {"port": 8222, "timeout": 20},
            },
        },
    },

    # ── AI Stack (NEW) ───────────────────────────────────────────
    "ai-fullstack": {
        "name": "AI Fullstack",
        "description": "Stack AI com FastAPI + Ollama + Qdrant + Redis + Streamlit — LLM local, vector DB, cache e dashboard",
        "tags": ["ai", "llm", "ollama", "qdrant", "streamlit", "fastapi"],
        "services": {
            "llm": {
                "runtime": "ollama",
                "start_cmd": "ollama serve",
                "port": 11434,
                "environment": {
                    "OLLAMA_HOST": "0.0.0.0:11434",
                    "OLLAMA_MODELS": ".gbit/data/ollama/models",
                },
                "healthcheck": {"port": 11434, "timeout": 20},
            },
            "vectordb": {
                "runtime": "qdrant",
                "start_cmd": "./qdrant --storage-path .gbit/data/qdrant --port 6333",
                "port": 6333,
                "environment": {
                    "QDRANT__SERVICE__GRPC_PORT": "6334",
                },
                "healthcheck": {"port": 6333, "timeout": 15},
            },
            "cache": {
                "runtime": "redis",
                "start_cmd": "redis-server --port 6379 --dir .gbit/data/cache",
                "port": 6379,
                "healthcheck": {"port": 6379, "timeout": 10},
            },
            "api": {
                "runtime": "python",
                "start_cmd": "uvicorn main:app --host 0.0.0.0 --port 8000 --reload",
                "build_cmd": "pip install -r requirements.txt",
                "build": ".",
                "port": 8000,
                "depends_on": ["llm", "vectordb", "cache"],
                "environment": {
                    "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
                    "QDRANT_URL": "http://127.0.0.1:6333",
                    "REDIS_URL": "redis://127.0.0.1:6379",
                    "PORT": "8000",
                },
                "healthcheck": {"port": 8000, "timeout": 25},
            },
            "dashboard": {
                "runtime": "python",
                "start_cmd": "streamlit run app.py --server.port 8501",
                "build_cmd": "pip install -r requirements.txt",
                "build": "./dashboard",
                "port": 8501,
                "depends_on": ["api"],
                "environment": {
                    "API_URL": "http://127.0.0.1:8000",
                },
                "healthcheck": {"port": 8501, "timeout": 25},
            },
        },
    },
}

# ── Stack Aliases ───────────────────────────────────────────────

STACK_ALIASES: Dict[str, str] = {
    "mern": "node-fullstack",
    "mean": "node-fullstack",
    "lamp": "laravel-fullstack",
    "django": "fastapi-backend",
    "flask": "fastapi-backend",
    "gin": "go-microservices",
    "actix": "rust-backend",
    "spring": "spring-backend",
    "rails": "rails-fullstack",
    "dotnet": "dotnet-backend",
    "node": "minimal",
    "mongo": "mongo-express",
    "postgres": "postgres-pgadmin",
    "redis": "redis-insight",
    "mysql": "mysql-phpmyadmin",
    "nats": "nats-streaming",
    "ai": "ai-fullstack",
    "ollama": "ai-fullstack",
    "llm": "ai-fullstack",
    "rag": "ai-fullstack",
}


# ── Helper Functions ──────────────────────────────────────────────

def get_stack(name: str) -> Optional[Dict[str, Any]]:
    """Get stack by name or alias"""
    # Direct lookup
    if name in STACKS:
        return STACKS[name]
    # Alias lookup
    if name in STACK_ALIASES:
        resolved = STACK_ALIASES[name]
        if resolved in STACKS:
            return STACKS[resolved]
    # Fuzzy match
    name_lower = name.lower().replace("-", "").replace("_", "")
    for key, stack in STACKS.items():
        key_norm = key.lower().replace("-", "").replace("_", "")
        if name_lower in key_norm or key_norm in name_lower:
            return stack
    return None


def list_stacks() -> List[Dict[str, Any]]:
    """List all available stacks"""
    result = []
    for key, stack in STACKS.items():
        result.append({
            "id": key,
            "name": stack.get("name", key),
            "description": stack.get("description", ""),
            "tags": stack.get("tags", []),
            "services": list(stack.get("services", {}).keys()),
        })
    return result


def get_stack_description(name: str) -> str:
    """Get description of a stack"""
    stack = get_stack(name)
    if not stack:
        return f"Stack '{name}' nao encontrada"
    services = stack.get("services", {})
    svc_list = ", ".join(f"{n}(:{s.get('port', '?')})" for n, s in services.items())
    return f"{stack.get('name', name)} — {stack.get('description', '')} | Servicos: {svc_list}"
 

# ── CLI Compatibility API ───────────────────────────────────────
# Compatibility layer used by gbit_container.cli.main

# Public name expected by the CLI
STACK_TEMPLATES = STACKS


def get_stack_names() -> List[str]:
    """Return the names of all available stack templates."""
    return list(STACKS.keys())


def resolve_stack_name(name: str) -> Optional[str]:
    """Resolve a stack name or alias to the canonical stack ID."""
    if not name:
        return None

    normalized = name.strip().lower()

    # Direct stack name
    if normalized in STACKS:
        return normalized

    # Alias
    if normalized in STACK_ALIASES:
        resolved = STACK_ALIASES[normalized]
        if resolved in STACKS:
            return resolved

    # Normalized comparison
    normalized_compact = normalized.replace("-", "").replace("_", "")

    for key in STACKS:
        key_compact = key.lower().replace("-", "").replace("_", "")

        if normalized_compact == key_compact:
            return key

    # Fuzzy match
    for key in STACKS:
        key_compact = key.lower().replace("-", "").replace("_", "")

        if (
            normalized_compact in key_compact
            or key_compact in normalized_compact
        ):
            return key

    return None


def get_all_stack_choices() -> List[str]:
    """Return stack names and aliases available to the CLI."""
    choices = list(STACKS.keys())

    for alias in STACK_ALIASES:
        if alias not in choices:
            choices.append(alias)

    return choices
