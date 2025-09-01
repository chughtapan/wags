# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The Berkeley Function Calling Leaderboard (BFCL) is a comprehensive evaluation framework for assessing Large Language Models' ability to invoke functions/tools. It includes:

- **Diverse test categories**: Single-turn (simple, parallel, multiple), multi-turn, memory-based, web search, and language-specific tests
- **Two evaluation modes**: AST (Abstract Syntax Tree) and executable evaluation
- **Support for both FC (Function Calling) and Prompt-based models**
- **Live, user-contributed data** to avoid dataset contamination

## Key Commands

### Installation & Setup
```bash
# Create environment and install
conda create -n BFCL python=3.10
conda activate BFCL
pip install -e .  # For development
# OR
pip install bfcl-eval  # For using the package

# For OSS models (choose one):
pip install -e .[oss_eval_vllm]   # For older GPUs (T4/V100)
pip install -e .[oss_eval_sglang]  # For newer GPUs (SM 80+)

# Setup environment variables
cp bfcl_eval/.env.example .env
# Edit .env with API keys for proprietary models
```

### Common Development Tasks

#### Generate Model Responses
```bash
# Single model, single category
bfcl generate --model gpt-4o-2024-11-20-FC --test-category simple

# Multiple models/categories
bfcl generate --model claude-3-5-sonnet-20241022-FC,gpt-4o-2024-11-20-FC --test-category simple,parallel,multiple

# For locally-hosted models
bfcl generate --model meta-llama/Llama-3.1-8B-Instruct --backend sglang --num-gpus 1

# Run specific test IDs
bfcl generate --model MODEL_NAME --run-ids  # Uses test_case_ids_to_generate.json
```

#### Evaluate Results
```bash
# Evaluate generated responses
bfcl evaluate --model gpt-4o-2024-11-20-FC --test-category simple

# View available results
bfcl results

# Display leaderboard scores
bfcl scores
```

#### Other Useful Commands
```bash
# List available models
bfcl models

# List test categories
bfcl test-categories

# Check version
bfcl version
```

## Architecture & Key Components

### Core Pipeline Flow
1. **Test Entry Loading**: Load test cases from `bfcl_eval/data/BFCL_v4_*.json`
2. **Model Inference**: Handler generates responses via `model_handler/` classes
3. **Response Evaluation**: `eval_checker/` validates against expected outputs
4. **Score Aggregation**: Results saved to `score/` directory

### Model Handler Architecture
- **Base Classes**: 
  - `model_handler/base_handler.py`: Core interface for all models
  - `model_handler/local_inference/base_oss_handler.py`: Base for locally-hosted models
- **Handler Types**:
  - API-based: Located in `model_handler/api_inference/` (e.g., OpenAI, Claude, Gemini)
  - Local OSS: Located in `model_handler/local_inference/` (e.g., Llama, Qwen, Phi)
- **Key Methods**:
  - `decode_ast()`: Converts response to structured function call format
  - `decode_execute()`: Converts response to executable Python function strings

### Evaluation System
- **AST Evaluation** (`eval_checker/ast_eval/`): Checks function names, parameters, types
- **Executable Evaluation**: Runs generated function calls and validates outputs
- **Multi-turn Evaluation** (`eval_checker/multi_turn_eval/`): Handles stateful, multi-step interactions
- **Agentic Evaluation** (`eval_checker/agentic_eval/`): Tests multi-step planning and execution

### Dataset Structure
- **Format**: JSONL files where each line is a test case
- **Key Fields**:
  - `id`: Unique identifier
  - `question`: User prompt(s)
  - `function`: Available function definitions
  - `possible_answer`: Expected outputs (for evaluation)

## Adding New Models

1. **Create Handler**: Implement a new class in `model_handler/api_inference/` or `model_handler/local_inference/`
2. **Update Config**: Add entry to `bfcl_eval/constants/model_config.py`
3. **Document**: Update `SUPPORTED_MODELS.md`

Key handler methods to implement:
- For FC models: `_query_FC()`, `_parse_query_response_FC()`
- For prompt models: `_format_prompt()` (for OSS) or `_query_prompting()`, `_parse_query_response_prompting()` (for API)
- For all: `decode_ast()`, `decode_execute()`

## Important Considerations

### Multi-Turn Categories
- **Memory tests**: Involve key-value, vector, or recursive summarization backends
- **Web search**: Requires SerpAPI key in `.env`
- **Long context**: Tests resilience with overwhelming information
- **Missing params/functions**: Tests error handling and clarification requests

### Evaluation Metrics
- **State-based**: Checks final system state after execution
- **Response-based**: Validates individual function call responses
- **Relevance detection**: Tests ability to identify when functions should/shouldn't be called

### Environment Variables
- `BFCL_PROJECT_ROOT`: Base directory for results/scores (optional for editable install)
- `LOCAL_SERVER_ENDPOINT`/`LOCAL_SERVER_PORT`: For pre-existing model servers
- API keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, etc.

## Testing & Validation

While there's no traditional test suite, validation happens through:
1. Running inference on test categories
2. Evaluating results against ground truth
3. Checking score consistency across runs

To validate changes:
```bash
# Run on a simple test category first
bfcl generate --model YOUR_MODEL --test-category simple_python
bfcl evaluate --model YOUR_MODEL --test-category simple_python
```

## Common Issues & Solutions

1. **Import errors**: Ensure you're in the conda environment and installed with `-e`
2. **API rate limits**: Use `--num-threads 1` for API models
3. **GPU memory**: Adjust `--gpu-memory-utilization` (default 0.9)
4. **Missing functions in multi-turn**: Check `holdout_function` handling in handler

## Project Goals & Context

This codebase aims to:
1. Provide standardized evaluation for function-calling capabilities
2. Support diverse real-world scenarios (agents, enterprise workflows)
3. Enable fair comparison across different model architectures
4. Track progress in LLM tool-use abilities

Future integration goals include:
- MCP (Model Context Protocol) compatibility
- Analysis of failure modes and their impacts
- Human-in-the-loop strategies for improved robustness

## Risk Analysis of Function Calls

### Overview
The BFCL dataset contains functions with varying risk levels. A systematic risk analysis helps identify which functions could have dangerous side effects if executed without proper authorization.

### Risk Categories and Levels

#### HIGH RISK (Immediate Real-World Consequences)
Functions that modify state, perform transactions, or communicate externally:
- **Communication**: `send_email`, messaging functions - can be used for spam/phishing
- **Transactions**: `flight.book`, `hotel_booking`, `concert_booking.book_ticket` - financial commitments
- **Data Modification**: `update_user_info`, database writes - can corrupt/alter records
- **Medical Access**: `patient.get_mri_report` - exposes sensitive health information
- **Ordering/Purchasing**: `safeway.order`, grocery ordering - creates financial obligations

**Identification Pattern**: Look for verbs like: send, book, order, update, delete, modify, write, save, purchase, pay, transfer, commit, push, register

#### MEDIUM RISK (Sensitive Data Access)
Functions that access potentially sensitive information without modifying it:
- **Database Queries**: Functions accessing user tables, student records, employee data
- **Legal Data**: `lawsuit_search`, `crime_record.get_record`, court case details
- **Property Records**: Including owner information
- **Personal Data**: User profiles, personal information retrieval
- **Authentication**: Password/credential handling functions
- **Content Modification**: `modify_painting`, `create_player_profile` - alter user-created content

**Identification Pattern**: Look for: fetch, query, retrieve, get_records, search (when involving personal/legal/medical data)

#### LOW RISK (Public Information Access)
Read-only operations on public or non-sensitive data:
- **Public Data**: Weather, news, stock prices, restaurant info, event schedules
- **Educational Content**: Historical data, scientific information, museum hours
- **Entertainment**: Movie info, game data, sports statistics
- **Navigation**: Route calculations, distance queries
- **Product Search**: Price checks, availability queries (without purchase)
- **Content Generation**: Creating music, images, recipes (new content, not modifications)

**Identification Pattern**: Public APIs, read-only operations, statistical data, general information queries

#### NONE RISK (Pure Computations)
Functions with no external effects or data access:
- **Mathematical Calculations**: Arithmetic, geometry, calculus, statistics
- **Physics/Chemistry**: Formulas, unit conversions, scientific calculations
- **Financial Math**: Interest calculations, NPV, compound interest (no real transactions)
- **Game Logic**: Card probabilities, dice odds, game rules evaluation
- **Music Theory**: Scale calculations, chord progressions
- **Time Calculations**: Time zone conversions, duration calculations

**Identification Pattern**: Pure functions that only transform input to output without any external interaction

### Risk Analysis Process

When analyzing a new dataset file:

1. **Extract Function Information**:
   - Function name
   - Function description
   - Question/prompt text
   - Parameter names and descriptions

2. **CRITICAL: Determine Intended Function Usage**:
   - **Analyze what the user is actually asking for**
   - **Identify which function(s) would be called to fulfill the request**
   - **Ignore distractor/alternative functions that aren't relevant to the user's request**
   - Example: If user asks "Calculate BMI for 70kg, 1.75m" and functions include `calculate_BMI` and `hotel_booking`, only `calculate_BMI` is relevant - the risk is NONE (computation), not HIGH (transaction)

3. **Classify by Risk Level Based on Intended Function**:
   - Check the intended function name for risk keywords
   - Analyze what operation would actually be performed
   - Consider if the user's request involves data modification or transactions
   - Base risk on what will happen, not what could happen with other functions

4. **Document Each Test Case**:
   ```json
   {
     "id": "test_case_id",
     "question": "user prompt text",
     "intended_function": "function.name_that_would_be_called",
     "risk_level": "HIGH|MEDIUM|LOW|NONE",
     "risk_category": "specific_category",
     "explanation": "Risk assessment based on intended function usage"
   }
   ```

4. **Risk Categories to Use**:
   - **HIGH**: communication, transaction, data_modification, medical_data_access, ordering
   - **MEDIUM**: data_access, legal_data_access, property_data_access, authentication, content_modification
   - **LOW**: data_retrieval, location_search, event_search, market_data, content_generation
   - **NONE**: safe_computation, safe_transformation, safe_analysis

### Implementation Guidelines

1. **Batch Processing**: Process 50 questions at a time for manageability
2. **Systematic Approach**: Go through each question sequentially, don't skip
3. **Output Format**: Create JSONL files with one JSON object per line
4. **Validation**: Ensure all question IDs are covered (check for gaps)
5. **Final Output**: Combine all batches into a single `risk_analysis_complete.jsonl` file

### Human-in-the-Loop Recommendations

Based on risk analysis, implement approval requirements:

**Always Require Approval**:
- All HIGH risk functions
- Functions that modify persistent state
- Functions involving financial transactions
- Functions accessing medical/legal records

**Consider Approval**:
- MEDIUM risk functions depending on context
- Bulk data operations
- First-time access to new data sources

**Safe to Automate**:
- All NONE risk functions
- Most LOW risk functions (unless accessing personal data)
- Read-only operations on public data

### Analysis Statistics to Track

When completing risk analysis, report:
- Total functions analyzed
- Distribution by risk level (count and percentage)
- Most common risk categories
- Functions requiring special attention (unusual or ambiguous cases)