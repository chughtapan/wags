#!/usr/bin/env python3
"""CLI interface for BFCL evaluation tool."""

import json
import sys
from pathlib import Path

import click

from .runner import run_test
from .bfcl.data_loader import load_test_entry
from .evaluator import evaluate_results


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """BFCL evaluation tool for fast-agent."""
    pass


@cli.command()
@click.argument("test_id")
@click.option("--model", default="gpt-4o", help="Model to use (default: gpt-4o)")
@click.option("--temperature", default=0.001, type=float, help="Temperature setting (default: 0.001)")
@click.option("--output-dir", type=click.Path(path_type=Path), default="outputs", help="Output directory (default: outputs)")
def run(test_id: str, model: str, temperature: float, output_dir: Path):
    """Run a single BFCL test."""
    try:
        # Load test case
        test_case = load_test_entry(test_id)
        
        click.echo(f"Running test: {test_id}")
        click.echo(f"Model: {model}")
        click.echo(f"Temperature: {temperature}")
        click.echo(f"Involved classes: {test_case.get('involved_classes', [])}")
        click.echo(f"Number of turns: {len(test_case.get('question', []))}")
        
        # Execute test
        result = run_test(test_case, model, temperature, output_dir)
        
        if result["success"]:
            click.secho("✓ Test executed successfully", fg="green")
            click.echo(f"Output file: {result['output_file']}")
        else:
            click.secho(f"✗ Test failed: {result.get('error', 'Unknown error')}", fg="red")
            if result.get("stderr"):
                click.echo(f"Error details: {result['stderr'][:500]}...")
                
    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red")
        sys.exit(1)


@cli.command()
@click.argument("test_id")
@click.argument("log_file", type=click.Path(exists=True))
def evaluate(test_id: str, log_file: str):
    """Evaluate test results against ground truth."""
    click.echo(f"Evaluating test: {test_id}")
    click.echo(f"Log file: {log_file}")
    
    try:
        evaluation = evaluate_results(test_id, log_file)
        
        # Display results
        validation_passed = evaluation["validation"].get("valid", False)
        irrelevance_passed = evaluation["irrelevance_check"].get("valid", False)
        
        click.echo("\nResults:")
        if validation_passed:
            click.secho(f"✓ Validation: PASSED", fg="green")
        else:
            click.secho(f"✗ Validation: FAILED", fg="red")
            
        if irrelevance_passed:
            click.secho(f"✓ Irrelevance Check: PASSED", fg="green")
        else:
            click.secho(f"✗ Irrelevance Check: FAILED", fg="red")
        
        # Show details
        click.echo(f"\nTurns processed: {len(evaluation['model_responses'])}")
        for i, turn in enumerate(evaluation['model_responses']):
            click.echo(f"  Turn {i+1}: {len(turn)} function calls")
        
        # Save results
        output_file = Path("outputs") / "evaluations" / f"{test_id}.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(evaluation, indent=2))
        click.echo(f"\nDetailed results saved to: {output_file}")
        
    except Exception as e:
        click.secho(f"✗ Evaluation error: {e}", fg="red")
        sys.exit(1)


@cli.command()
@click.argument("test_id")
@click.option("--model", default="gpt-4o", help="Model to use")
@click.option("--temperature", default=0.001, type=float, help="Temperature setting")
@click.option("--output-dir", type=click.Path(path_type=Path), default="outputs", help="Output directory")
def test(test_id: str, model: str, temperature: float, output_dir: Path):
    """Run test and evaluate results in one command."""
    try:
        # Load test case
        test_case = load_test_entry(test_id)
        
        click.echo(f"Running test: {test_id}")
        click.echo(f"Model: {model}")
        
        # Execute test
        result = run_test(test_case, model, temperature, output_dir)
        
        if not result["success"]:
            click.secho(f"✗ Test execution failed: {result.get('error', 'Unknown error')}", fg="red")
            sys.exit(1)
        
        click.secho("✓ Test executed successfully", fg="green")
        
        # Evaluate results
        click.echo("\nEvaluating results...")
        evaluation = evaluate_results(test_id, result["output_file"])
        
        # Display summary
        validation_passed = evaluation["validation"].get("valid", False)
        irrelevance_passed = evaluation["irrelevance_check"].get("valid", False)
        
        if validation_passed and irrelevance_passed:
            click.secho("\n✓ All checks PASSED", fg="green", bold=True)
        else:
            click.secho("\n✗ Some checks FAILED", fg="red", bold=True)
            click.echo(f"  Validation: {'PASSED' if validation_passed else 'FAILED'}")
            click.echo(f"  Irrelevance: {'PASSED' if irrelevance_passed else 'FAILED'}")
        
        # Save evaluation
        eval_file = output_dir / "evaluations" / f"{test_id}.json"
        eval_file.parent.mkdir(parents=True, exist_ok=True)
        eval_file.write_text(json.dumps(evaluation, indent=2))
        click.echo(f"\nResults saved to: {eval_file}")
        
    except Exception as e:
        click.secho(f"✗ Error: {e}", fg="red")
        sys.exit(1)



if __name__ == "__main__":
    cli()