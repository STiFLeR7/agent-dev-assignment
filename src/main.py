import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .orchestrator import InvoiceReconciliationWorkflow
from .config import INVOICE_FILES, OUTPUT_DIR

console = Console()

def parse_args():
    
    parser = argparse.ArgumentParser(
        description="Invoice Reconciliation Multi-Agent System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=
    )
    
    parser.add_argument(
        "--invoice", "-i",
        type=str,
        help="Path to a single invoice to process (default: process all test invoices)"
    )
    
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output JSON file path (default: output/results_<timestamp>.json)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show verbose output"
    )
    
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="OpenAI API key (default: use OPENAI_API_KEY env var)"
    )
    
    return parser.parse_args()

def display_results_table(results):
    
    table = Table(title="Invoice Processing Results", show_header=True, header_style="bold magenta")
    
    table.add_column("Invoice", style="cyan")
    table.add_column("Supplier", style="white")
    table.add_column("Total", justify="right", style="green")
    table.add_column("PO Match", style="yellow")
    table.add_column("Discrepancies", justify="center")
    table.add_column("Recommendation", style="bold")
    table.add_column("Confidence", justify="right")
    
    for result in results:
        pr = result.processing_results
        
        action = pr.recommended_action.value
        if action == "auto_approve":
            action_display = "[green]✅ AUTO-APPROVE[/green]"
        elif action == "flag_for_review":
            action_display = "[yellow]🔶 REVIEW[/yellow]"
        else:
            action_display = "[red]🔴 ESCALATE[/red]"
        
        table.add_row(
            pr.extracted_data.invoice_number,
            pr.extracted_data.supplier_name[:25] + "..." if len(pr.extracted_data.supplier_name) > 25 else pr.extracted_data.supplier_name,
            f"£{pr.extracted_data.total:,.2f}",
            pr.matching_results.matched_po if pr.matching_results and pr.matching_results.matched_po else "None",
            str(len(pr.discrepancies)),
            action_display,
            f"{pr.confidence*100:.0f}%",
        )
    
    console.print(table)

def display_discrepancy_details(results):
    
    for result in results:
        pr = result.processing_results
        
        if pr.discrepancies:
            console.print(f"\n[bold cyan]Discrepancies for {pr.extracted_data.invoice_number}:[/bold cyan]")
            
            for disc in pr.discrepancies:
                severity_color = {
                    "low": "green",
                    "medium": "yellow", 
                    "high": "red",
                    "critical": "bold red",
                }.get(disc.severity.value, "white")
                
                console.print(f"  [{severity_color}]• {disc.type.value}[/{severity_color}]: {disc.details}")

def save_results(results, output_path):
    
    output_data = {
        "processing_timestamp": datetime.now().isoformat() + "Z",
        "total_invoices": len(results),
        "results": [r.model_dump() for r in results],
        "summary": {
            "auto_approve": sum(1 for r in results if r.processing_results.recommended_action.value == "auto_approve"),
            "flag_for_review": sum(1 for r in results if r.processing_results.recommended_action.value == "flag_for_review"),
            "escalate_to_human": sum(1 for r in results if r.processing_results.recommended_action.value == "escalate_to_human"),
        }
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, default=str)
    
    console.print(f"\n[green]Results saved to: {output_path}[/green]")

def main():
    
    args = parse_args()
    
    console.print(Panel.fit(
        "[bold blue]Invoice Reconciliation Multi-Agent System[/bold blue]\n"
        "[dim]Powered by LangGraph + GPT-4o Vision[/dim]",
        border_style="blue"
    ))
    
    try:
        workflow = InvoiceReconciliationWorkflow(api_key=args.api_key)
    except Exception as e:
        console.print(f"[red]Error initializing workflow: {e}[/red]")
        console.print("[yellow]Make sure OPENAI_API_KEY is set in your environment or .env file[/yellow]")
        sys.exit(1)
    
    if args.invoice:
        invoice_path = Path(args.invoice)
        if not invoice_path.exists():
            console.print(f"[red]Error: Invoice file not found: {args.invoice}[/red]")
            sys.exit(1)
        invoice_paths = [str(invoice_path)]
    else:
        invoice_paths = [str(f) for f in INVOICE_FILES if f.exists()]
        
        if not invoice_paths:
            console.print("[red]Error: No invoice files found in the expected location[/red]")
            sys.exit(1)
    
    console.print(f"\n[cyan]Processing {len(invoice_paths)} invoice(s)...[/cyan]\n")
    
    start_time = datetime.now()
    results = workflow.process_all_invoices(invoice_paths)
    total_time = (datetime.now() - start_time).total_seconds()
    
    console.print("\n")
    display_results_table(results)
    
    if args.verbose:
        display_discrepancy_details(results)
    
    console.print(f"\n[dim]Total processing time: {total_time:.2f}s ({total_time/len(results):.2f}s per invoice)[/dim]")
    
    console.print("\n[bold]Critical Test Results:[/bold]")
    
    invoice_4_results = [r for r in results if "4" in r.document_info.filename or "Price" in r.document_info.filename]
    if invoice_4_results:
        r = invoice_4_results[0]
        price_discrepancies = [d for d in r.processing_results.discrepancies if d.type.value == "price_mismatch"]
        if price_discrepancies:
            console.print("[green]  ✓ Invoice 4: Price discrepancy detected![/green]")
            for pd in price_discrepancies:
                console.print(f"    {pd.details}")
        else:
            console.print("[red]  ✗ Invoice 4: Price discrepancy NOT detected[/red]")
    
    invoice_5_results = [r for r in results if "5" in r.document_info.filename or "Missing" in r.document_info.filename]
    if invoice_5_results:
        r = invoice_5_results[0]
        if r.processing_results.matching_results and r.processing_results.matching_results.matched_po:
            console.print(f"[green]  ✓ Invoice 5: Fuzzy matched to {r.processing_results.matching_results.matched_po}[/green]")
        else:
            console.print("[yellow]  ⚠ Invoice 5: Could not fuzzy match to PO[/yellow]")
    
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUT_DIR / f"results_{timestamp}.json"
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_results(results, output_path)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
