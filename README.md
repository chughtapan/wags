# Elicitation Evaluations

Evaluation scripts for testing MCP (Model Context Protocol) elicitation with BFCL (Berkeley Function Call Leaderboard) integration.

## Overview

This repository contains scripts to evaluate how human-in-the-loop elicitation improves LLM function-calling accuracy using the BFCL benchmark.

## Setup

```bash
# Clone with submodules
git clone --recursive <repository-url>
cd elicitation_evals

# Install dependencies
pip install mcp

# Install BFCL dependencies (if needed)
cd bfcl/berkeley-function-call-leaderboard
pip install -r requirements.txt
```

## Usage

### Running the MCP Server

```bash
# Run directly from source
cd src/elicitation_evals/mcp_servers
python bfcl_api_server.py TwitterAPI

# With scenario from BFCL test data
python bfcl_api_server.py TwitterAPI \
    ../../../bfcl/berkeley-function-call-leaderboard/bfcl_eval/data/BFCL_v4_multi_turn_base.json \
    multi_turn_base_0

# Test with MCP Inspector
npx @modelcontextprotocol/inspector python bfcl_api_server.py TwitterAPI
```

### Available API Classes

- `TwitterAPI` - Social media operations
- `GorillaFileSystem` - File system operations
- `MathAPI` - Mathematical calculations
- `MessageAPI` - Messaging functionality
- `TicketAPI` - Ticket management
- `TradingBot` - Trading operations
- `TravelAPI` - Travel booking
- `VehicleControlAPI` - Vehicle control
- `WebSearchAPI` - Web search
- `MemoryAPI_kv` - Key-value memory
- `MemoryAPI_vector` - Vector memory
- `MemoryAPI_rec_sum` - Recursive summarization

## Project Structure

```
elicitation_evals/
├── src/
│   └── elicitation_evals/
│       └── mcp_servers/
│           └── bfcl_api_server.py   # MCP server wrapper
├── bfcl/                             # BFCL submodule
│   └── berkeley-function-call-leaderboard/
├── CLAUDE.md                         # Claude AI instructions
├── pyproject.toml                    # Project dependencies
└── README.md
```

## Development

```bash
# Format code
black src/
ruff check src/

# Run tests
pytest
```

## License

MIT