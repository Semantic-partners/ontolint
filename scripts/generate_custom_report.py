#!/usr/bin/env python3
"""
Generate a custom markdown report from aggregated CTRF JSON files.
Uses Handlebars template to render the report.
"""

import json
import os
import glob
from pathlib import Path
from datetime import datetime
import argparse

def aggregate_ctrf_reports(ctrf_dir):
    """Load and aggregate all CTRF JSON files from the specified directory."""
    reports = []
    ctrf_files = glob.glob(os.path.join(ctrf_dir, '*.json'))
    
    if not ctrf_files:
        print(f"Warning: No CTRF JSON files found in {ctrf_dir}")
        return reports
    
    total_tests = 0
    total_passed = 0
    total_failed = 0
    
    for ctrf_file in sorted(ctrf_files):
        try:
            with open(ctrf_file, 'r') as f:
                ctrf_data = json.load(f)
            
            # Extract ontology name from filename
            ontology_file = Path(ctrf_file).stem
            
            # Count failed tests for this report
            failed_tests = [t for t in ctrf_data['results']['tests'] if t['status'] == 'failed']
            
            report_entry = {
                'ontologyFile': ontology_file,
                'results': ctrf_data['results'],
                'failedTests': failed_tests,
                'hasFailures': len(failed_tests) > 0
            }
            
            reports.append(report_entry)
            
            # Accumulate totals
            total_tests += ctrf_data['results']['summary']['tests']
            total_passed += ctrf_data['results']['summary']['passed']
            total_failed += ctrf_data['results']['summary']['failed']
            
        except json.JSONDecodeError as e:
            print(f"Error parsing {ctrf_file}: {e}")
        except KeyError as e:
            print(f"Error: Missing expected key in {ctrf_file}: {e}")
    
    return reports, total_tests, total_passed, total_failed


def simple_handlebars_render(template_content, context):
    """
    Simple Handlebars-like template rendering.
    Supports: {{#each}}, {{/each}}, {{variable}}, {{#if}}, {{/if}}, {{else}}
    Handles nested {{#each}} blocks properly.
    """
    import re
    
    # Helper to check equality
    context['eq'] = lambda a, b: a == b
    
    def find_matching_end(template, start_pos, block_type):
        """Find the matching {{/blocktype}} for a {{#blocktype}} at start_pos."""
        depth = 1
        open_pattern = '{{#' + block_type
        close_pattern = '{{/' + block_type + '}}'
        
        pos = start_pos
        while pos < len(template):
            open_idx = template.find(open_pattern, pos)
            close_idx = template.find(close_pattern, pos)
            
            if close_idx == -1:
                return None, None  # No matching close tag
            
            if open_idx != -1 and open_idx < close_idx:
                depth += 1
                pos = open_idx + len(open_pattern)
            else:
                depth -= 1
                if depth == 0:
                    return close_idx, close_idx + len(close_pattern)
                pos = close_idx + len(close_pattern)
        
        return None, None
    
    def render_recursive(template, ctx):
        """Recursively render template, handling nested structures."""
        output = template
        
        # Process {{#each}} blocks (process outermost first, then recurse into content)
        each_start_pattern = r'\{\{#each\s+(\w+(?:\.\w+)*)\}\}'
        
        while True:
            match = re.search(each_start_pattern, output)
            if not match:
                break
            
            var_path = match.group(1)
            block_start = match.start()
            content_start = match.end()
            
            # Find matching {{/each}}
            block_end, end_pos = find_matching_end(output, content_start, 'each')
            if block_end is None:
                break  # Malformed template
            
            # Extract block content
            block_content = output[content_start:block_end]
            
            # Get the items list
            items = get_nested_value(ctx, var_path)
            if not isinstance(items, list):
                items = []
            
            # Render content for each item
            result_items = []
            for item in items:
                # Create new context for this iteration, preserving parent context
                item_context = ctx.copy()
                if isinstance(item, dict):
                    item_context.update(item)
                
                # Recursively render the block content with item context
                rendered_block = render_recursive(block_content, item_context)
                result_items.append(rendered_block)
            
            # Replace the entire {{#each}}...{{/each}} block
            replacement = ''.join(result_items)
            output = output[:block_start] + replacement + output[end_pos:]
        
        # Process {{#if}} blocks
        if_pattern = r'\{\{#if\s+([^}]+)\}\}(.*?)(?:\{\{else\}\}(.*?))?\{\{/if\}\}'
        
        def replace_if(match):
            condition = match.group(1).strip()
            true_block = match.group(2)
            false_block = match.group(3) or ''
            
            # Simple condition evaluation
            result = evaluate_condition(condition, ctx)
            return true_block if result else false_block
        
        output = re.sub(if_pattern, replace_if, output, flags=re.DOTALL)
        
        # Process simple variables {{variable}}
        var_pattern = r'\{\{([^#/}]+)\}\}'
        
        def replace_var(match):
            var_path = match.group(1).strip()
            val = get_nested_value(ctx, var_path)
            # Handle callables (like functions)
            if callable(val):
                return ''
            return str(val) if val is not None else ''
        
        output = re.sub(var_pattern, replace_var, output)
        
        return output
    
    return render_recursive(template_content, context)


def get_nested_value(obj, path):
    """Get nested value from object using dot notation."""
    if not path:
        return obj
    
    keys = path.split('.')
    current = obj
    
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
            if current is None:
                return ''
        else:
            return ''
    
    return current


def evaluate_condition(condition, context):
    """Evaluate simple conditions."""
    # Handle (eq x y) function calls
    import re
    eq_pattern = r'\(eq\s+(\S+)\s+(\S+)\)'
    
    def replace_eq(match):
        left = match.group(1)
        right = match.group(2)
        left_val = get_nested_value(context, left)
        right_val = right.strip('"\'')  # Remove quotes
        return 'true' if left_val == right_val else 'false'
    
    condition = re.sub(eq_pattern, replace_eq, condition)
    
    # Simple boolean evaluation
    return condition.lower() not in ['false', '0', '', 'none', 'null']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ctrf-dir', type=str, metavar='directory', default='ctrf', help='Directory to write CTRF report to.')
    parser.add_argument('--template-path', type=str, metavar='directory', default='templates/ctrf-report.hbs', help='Path to the CTRF report template file.')
    parser.add_argument('--output-path', type=str, metavar='directory', default='out/ctrf_report.md', help='Path to write the CTRF markdown report file.')

    args = parser.parse_args()

    print(f"Loading CTRF reports from: {args.ctrf_dir}")
    print(f"Template file: {args.template_path}")
    print(f"Output file: {args.output_path}")
    
    # Load template
    if not os.path.exists(args.template_path):
        print(f"Error: Template file not found: {args.template_path}")
        return 1
    
    with open(args.template_path, 'r') as f:
        template_content = f.read()
    
    # Aggregate reports
    reports, total_tests, total_passed, total_failed = aggregate_ctrf_reports(args.ctrf_dir)
    
    if not reports:
        print("No reports to process.")
        return 1
    
    # Prepare context for template rendering
    context = {
        'reports': reports,
        'totalTests': total_tests,
        'totalPassed': total_passed,
        'totalFailed': total_failed,
        'generatedAt': datetime.now().isoformat()
    }
    
    # Render template
    rendered_report = simple_handlebars_render(template_content, context)
    
    # Write output
    os.makedirs(os.path.dirname(args.output_path) or '.', exist_ok=True)
    with open(args.output_path, 'w') as f:
        f.write(rendered_report)
    
    print(f"\nCustom report generated: {args.output_path}")
    print(f"Total: {total_tests} tests | {total_passed} passed | {total_failed} failed")
    
    return 0


if __name__ == '__main__':
    exit(main())
