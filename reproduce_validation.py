
import asyncio
import json
from pathlib import Path
import sys

# Add project root to path
sys.path.append("/Users/parthkotwal/Projects/wags")

from tests.benchmarks.bfcl.test_bfcl import _validate_from_complete_json

async def main():
    test_id = "multi_turn_base_97"
    complete_path = Path("outputs/feedback/with_feed_fix_v10/raw/multi_turn_base_97_complete.json")
    
    try:
        evaluation = _validate_from_complete_json(test_id, complete_path)
        print(json.dumps(evaluation, indent=2))
    except Exception as e:
        print(f"Error during validation: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
