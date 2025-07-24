# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# 아임웹 AI Agent 서버

## 프로젝트 개요

아임웹 쇼핑몰 운영자가 쇼핑몰 관리를 쉽게 하도록 돕는 AI 에이전트를 만드는 프로젝트입니다. FastAPI와 MCP(Model Context Protocol) 서버를 통해 AI 기반 쇼핑몰 관리 솔루션을 제공합니다.

## Development Commands

### Package Management
- `uv sync` - Install dependencies (uses uv instead of pip for faster package management)
- `uv add <package>` - Add new dependency
- `uv remove <package>` - Remove dependency

### Running Services
- **Main Server**: `cd src/app && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
- **MCP Server**: `cd src/mcp && python imweb-mcp-server.py`
- **Docker Development**: `docker-compose up --build`
- **Playwright Install**: `playwright install` (required for web automation tools)

### Testing & Quality
- No specific test commands configured - investigate existing test setup in `src/app/tests/`

## High-Level Architecture

### Microservices Structure
The system uses a **dual-server architecture**:

1. **Main FastAPI Server** (`src/app/`) - Port 8000
   - REST API gateway for client interactions
   - Authentication, site management, script deployment
   - AI conversation threading through Google Gemini

2. **MCP Server** (`src/mcp/`) - Port 8001  
   - Specialized AI tools server using Model Context Protocol
   - Web automation via Playwright
   - Imweb-specific operations (products, promotions, community)

### Core Architecture Patterns

**Dependency Injection Container** (`src/app/core/`):
- `container.py` - IoC container managing service dependencies
- `factory.py` - Service factory with lifecycle management
- `interfaces.py` - Service contracts/interfaces
- All services are injected through the container for testability

**Service Layer** (`src/app/services/`):
- `ai_service.py` - Google Gemini integration + MCP client communication
- `auth_service.py` - Supabase authentication 
- `imweb_service.py` - OAuth2 integration with Imweb API
- `script_service.py` - Custom script deployment to Imweb sites
- `thread_service.py` - AI conversation context management

**MCP Tools Architecture** (`src/mcp/tools/`):
- Each tool provides specialized capabilities to AI agents
- `site_info.py` - Web scraping and site analysis
- `script.py` - Script execution and management
- `product.py`, `promotion.py`, `community.py` - Domain-specific operations
- Tools communicate back to main server for data persistence

### Data Flow & Integration Points

```
Client → FastAPI (8000) → AI Service → MCP Server (8001) → Imweb API
                ↓                           ↓
           Supabase DB ←← Thread Storage ←←←
```

**Key Integration Points**:
- **Supabase**: User auth, site configs, script storage, conversation threads
- **Imweb OAuth2**: Site access and management permissions  
- **Google Gemini**: AI conversation and tool selection
- **Playwright**: Automated web interactions for site analysis

### Configuration Management
- `src/app/core/config.py` - Pydantic Settings with environment variable binding
- Environment variables required: Supabase credentials, Imweb OAuth2, Gemini API key, JWT secrets
- Docker deployment uses container environment injection

### Error Handling & Responses
- `src/app/core/middleware.py` - Global exception handling
- `src/app/core/responses.py` - Standardized API response formats
- Pydantic schemas in `src/app/schemas.py` ensure type safety

## Technology Stack Specifics

- **Python 3.12+** with modern async/await patterns
- **FastAPI** for REST API with automatic OpenAPI documentation  
- **FastMCP** for Model Context Protocol server implementation
- **Pydantic v2** for data validation and settings management
- **Supabase** as primary database and auth provider
- **Playwright** for web automation and site scraping
- **uv** package manager (faster alternative to pip/poetry)

## Development Environment Setup

1. Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Install dependencies: `uv sync`
3. Install Playwright browsers: `playwright install`
4. Set up environment variables for Supabase, Imweb, and Gemini
5. Run both servers for full functionality

## Docker Deployment

The system uses multi-container deployment:
- `Dockerfile.main` - FastAPI server with Python dependencies
- `Dockerfile.mcp` - MCP server container
- `Dockerfile.playwright` - Playwright browser automation environment
- `docker-compose.yml` - Orchestrates services with internal networking

Main server exposes port 80 (mapped from 8000), MCP server runs internally on 8001.