"""
Generate classic CS algorithm diagrams for bisectors.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Rectangle, FancyArrowPatch, PathPatch
from matplotlib.path import Path
from typing import Optional

# Global constants for consistent diagram sizing
DIAGRAM_FIGSIZE = (16, 10)  # Standard figure size for most diagrams
EXECUTION_STRATEGY_FIGSIZE = (20, 12)  # Larger figure for execution strategy diagram
DIAGRAM_DPI = 150  # Standard DPI for all diagrams


def draw_column_bisector_diagram(
    output_path: Optional[str] = None,
    dpi: int = DIAGRAM_DPI,
    show: bool = False,
) -> None:
    """
    Draw a classic CS algorithm diagram showing the column bisector algorithm.
    
    Shows:
    - A data grid with rows and columns
    - Error cells highlighted in pink
    - A bisection tree showing the divide-and-conquer process
    - The expression line: df.select([pl.all().sum(), pl.all().mean(), pl.all().buggy()])
    """
    fig = plt.figure(figsize=DIAGRAM_FIGSIZE)
    
    # Create a custom grid layout
    gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3,
                         left=0.05, right=0.95, top=0.95, bottom=0.05)
    
    # Top section for title and code
    ax_title = fig.add_subplot(gs[0, :])
    ax_title.axis('off')
    
    # Left section for data grid
    ax_grid = fig.add_subplot(gs[1:, 0])
    
    # Right section for bisection tree
    ax_tree = fig.add_subplot(gs[1:, 1])
    
    # === Title and Code Section ===
    ax_title.text(0.5, 0.8, 'COLUMN BISECTOR', 
                 ha='center', va='top', fontsize=24, fontweight='bold',
                 family='monospace')
    
    # Code block with proper formatting
    code_lines = [
        "df.select([",
        "    pl.all().sum(),",
        "    pl.all().mean(),",
        "    pl.all().buggy()])",
    ]
    code_text = "\n".join(code_lines)
    ax_title.text(0.1, 0.5, code_text,
                 ha='left', va='center', fontsize=12, family='monospace',
                 bbox=dict(boxstyle='round', facecolor='#f0f0f0', edgecolor='#666', pad=10))
    
    ax_title.text(0.5, 0.2, 'Delta-Debugging Algorithm',
                 ha='center', va='bottom', fontsize=12, style='italic', color='#666')
    
    # === Data Grid Section ===
    ax_grid.set_xlim(-0.5, 5.5)
    ax_grid.set_ylim(-0.5, 9.5)
    ax_grid.set_aspect('equal')
    ax_grid.axis('off')
    ax_grid.set_title('Dataframe', fontsize=14, fontweight='bold', pad=20)
    
    # Draw grid with 9 rows and 3 columns
    num_rows = 9
    num_cols = 3
    cell_size = 0.8
    
    error_cells = [(2, 2), (4, 2), (7, 2)]  # (row, col) - 0-indexed, column C is index 2
    
    for i in range(num_rows):
        for j in range(num_cols):
            x = j * (cell_size + 0.1) + 0.5
            y = (num_rows - 1 - i) * (cell_size + 0.1) + 0.5
            
            is_error = (i, j) in error_cells
            
            if is_error:
                # Error cell - pink/red
                rect = Rectangle((x, y), cell_size, cell_size,
                               facecolor='#ffb6c1', edgecolor='#333333', linewidth=2)
            else:
                # Normal cell
                rect = Rectangle((x, y), cell_size, cell_size,
                               facecolor='white', edgecolor='#e0e0e0', linewidth=1.2)
            ax_grid.add_patch(rect)
            
            # Column labels (A, B, C)
            if i == 0:
                col_label = chr(65 + j)  # A, B, C
                ax_grid.text(x + cell_size/2, y + cell_size + 0.15, col_label,
                           ha='center', va='bottom', fontsize=12, fontweight='bold')
            
            # Row numbers
            if j == 0:
                ax_grid.text(x - 0.15, y + cell_size/2, str(i),
                           ha='right', va='center', fontsize=10, fontweight='bold')
    
    # === Bisection Tree Section ===
    ax_tree.set_xlim(0, 10)
    ax_tree.set_ylim(0, 10)
    ax_tree.set_aspect('equal')
    ax_tree.axis('off')
    ax_tree.set_title('Bisection Tree', fontsize=14, fontweight='bold', pad=20)
    
    # Root: All columns [A, B, C]
    root_x, root_y = 5, 9
    ax_tree.text(root_x, root_y, '[A, B, C]', ha='center', va='center',
                fontsize=11, fontweight='bold', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#ffcccc', edgecolor='red', linewidth=2))
    ax_tree.text(root_x, root_y - 0.4, '✗ FAIL', ha='center', va='top',
                fontsize=10, color='red', fontweight='bold')
    
    # Level 1: Split into [A, B] and [C]
    left1_x, left1_y = 2, 6.5
    right1_x, right1_y = 8, 6.5
    
    # Draw connecting lines
    ax_tree.plot([root_x, left1_x], [root_y - 0.3, left1_y + 0.3], 'k-', linewidth=2, alpha=0.6)
    ax_tree.plot([root_x, right1_x], [root_y - 0.3, right1_y + 0.3], 'k-',
                linewidth=2, alpha=0.6)
    
    # Left child: [A, B]
    ax_tree.text(left1_x, left1_y, '[A, B]', ha='center', va='center',
                fontsize=10, fontweight='bold', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#ccffcc', edgecolor='green', linewidth=2))
    ax_tree.text(left1_x, left1_y - 0.4, '✓ PASS', ha='center', va='top',
                fontsize=10, color='green', fontweight='bold')
    
    # Right child: [C]
    ax_tree.text(right1_x, right1_y, '[C]', ha='center', va='center',
                fontsize=10, fontweight='bold', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#ffcccc', edgecolor='red', linewidth=2))
    ax_tree.text(right1_x, right1_y - 0.4, '✗ FAIL', ha='center', va='top',
                fontsize=10, color='red', fontweight='bold')
    
    # Result annotation
    ax_tree.text(5, 3, 'Minimal Failing Set: [C]', ha='center', va='center',
                fontsize=12, fontweight='bold', family='monospace',
                bbox=dict(boxstyle='round,pad=0.8', facecolor='#ffffcc', edgecolor='orange', linewidth=2))
    
    plt.tight_layout()
    
    if output_path is None:
        output_path = 'column_bisector_diagram.png'
    
    plt.savefig(output_path, dpi=dpi, bbox_inches='tight')
    
    if show:
        plt.show()
    else:
        plt.close()


def draw_expression_bisector_diagram(
    output_path: Optional[str] = None,
    dpi: int = DIAGRAM_DPI,
    show: bool = False,
) -> None:
    """
    Draw a classic CS algorithm diagram showing the expression bisector algorithm.
    
    Shows:
    - A list of expressions
    - A bisection tree showing the divide-and-conquer process
    """
    fig = plt.figure(figsize=DIAGRAM_FIGSIZE)
    
    # Create a custom grid layout
    gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3,
                         left=0.05, right=0.95, top=0.95, bottom=0.05)
    
    # Top section for title
    ax_title = fig.add_subplot(gs[0, :])
    ax_title.axis('off')
    
    # Left section for expressions
    ax_expr = fig.add_subplot(gs[1:, 0])
    
    # Right section for bisection tree
    ax_tree = fig.add_subplot(gs[1:, 1])
    
    # === Title Section ===
    ax_title.text(0.5, 0.5, 'EXPRESSION BISECTOR', 
                 ha='center', va='center', fontsize=24, fontweight='bold',
                 family='monospace')
    
    # === Expressions Section ===
    ax_expr.set_xlim(0, 10)
    ax_expr.set_ylim(0, 10)
    ax_expr.set_aspect('equal')
    ax_expr.axis('off')
    ax_expr.set_title('Expressions', fontsize=14, fontweight='bold', pad=20)
    
    expressions = ['sum()', 'mean()', 'buggy()']
    expr_y_start = 7
    
    for i, expr in enumerate(expressions):
        y = expr_y_start - i * 2
        # Expression box
        rect = Rectangle((2, y - 0.4), 6, 0.8,
                        facecolor='white', edgecolor='#333', linewidth=2)
        ax_expr.add_patch(rect)
        ax_expr.text(5, y, expr, ha='center', va='center',
                    fontsize=12, fontweight='bold', family='monospace')
        
        if expr == 'buggy()':
            # Mark as error
            ax_expr.text(8.5, y, '✗', ha='center', va='center',
                        fontsize=14, color='red', fontweight='bold')
    
    # === Bisection Tree Section ===
    ax_tree.set_xlim(0, 10)
    ax_tree.set_ylim(0, 10)
    ax_tree.set_aspect('equal')
    ax_tree.axis('off')
    ax_tree.set_title('Bisection Tree', fontsize=14, fontweight='bold', pad=20)
    
    # Root: All expressions [sum(), mean(), buggy()]
    root_x, root_y = 5, 9
    ax_tree.text(root_x, root_y, '[sum(), mean(), buggy()]', ha='center', va='center',
                fontsize=10, fontweight='bold', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#ffcccc', edgecolor='red', linewidth=2))
    ax_tree.text(root_x, root_y - 0.4, '✗ FAIL', ha='center', va='top',
                fontsize=10, color='red', fontweight='bold')
    
    # Level 1: Split into [sum()] and [mean(), buggy()]
    left1_x, left1_y = 2, 6.5
    right1_x, right1_y = 8, 6.5
    
    # Draw connecting lines
    ax_tree.plot([root_x, left1_x], [root_y - 0.3, left1_y + 0.3], 'k-', linewidth=2, alpha=0.6)
    ax_tree.plot([root_x, right1_x], [root_y - 0.3, right1_y + 0.3], 'k-',
                linewidth=2, alpha=0.6)
    
    # Left child: [sum()]
    ax_tree.text(left1_x, left1_y, '[sum()]', ha='center', va='center',
                fontsize=10, fontweight='bold', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#ccffcc', edgecolor='green', linewidth=2))
    ax_tree.text(left1_x, left1_y - 0.4, '✓ PASS', ha='center', va='top',
                fontsize=10, color='green', fontweight='bold')
    
    # Right child: [mean(), buggy()]
    ax_tree.text(right1_x, right1_y, '[mean(), buggy()]', ha='center', va='center',
                fontsize=9, fontweight='bold', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#ffcccc', edgecolor='red', linewidth=2))
    ax_tree.text(right1_x, right1_y - 0.4, '✗ FAIL', ha='center', va='top',
                fontsize=10, color='red', fontweight='bold')
    
    # Level 2: Split [mean(), buggy()] into [mean()] and [buggy()]
    left2_x, left2_y = 6, 4
    right2_x, right2_y = 10, 4
    
    # Draw connecting lines from right1
    ax_tree.plot([right1_x, left2_x], [right1_y - 0.3, left2_y + 0.3], 'k-', linewidth=2, alpha=0.6)
    ax_tree.plot([right1_x, right2_x], [right1_y - 0.3, right2_y + 0.3], 'k-',
                linewidth=2, alpha=0.6)
    
    # Left child of right1: [mean()]
    ax_tree.text(left2_x, left2_y, '[mean()]', ha='center', va='center',
                fontsize=10, fontweight='bold', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#ccffcc', edgecolor='green', linewidth=2))
    ax_tree.text(left2_x, left2_y - 0.4, '✓ PASS', ha='center', va='top',
                fontsize=10, color='green', fontweight='bold')
    
    # Right child of right1: [buggy()]
    ax_tree.text(right2_x, right2_y, '[buggy()]', ha='center', va='center',
                fontsize=10, fontweight='bold', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#ffcccc', edgecolor='red', linewidth=2))
    ax_tree.text(right2_x, right2_y - 0.4, '✗ FAIL', ha='center', va='top',
                fontsize=10, color='red', fontweight='bold')
    
    # Result annotation
    ax_tree.text(5, 1.5, 'Minimal Failing Set: [buggy()]', ha='center', va='center',
                fontsize=12, fontweight='bold', family='monospace',
                bbox=dict(boxstyle='round,pad=0.8', facecolor='#ffffcc', edgecolor='orange', linewidth=2))
    
    plt.tight_layout()
    
    if output_path is None:
        output_path = 'expression_bisector_diagram.png'
    
    plt.savefig(output_path, dpi=dpi, bbox_inches='tight')
    
    if show:
        plt.show()
    else:
        plt.close()


def draw_row_range_bisector_diagram(
    output_path: Optional[str] = None,
    dpi: int = DIAGRAM_DPI,
    show: bool = False,
) -> None:
    """
    Draw a classic CS algorithm diagram showing the row range bisector algorithm.
    """
    fig = plt.figure(figsize=DIAGRAM_FIGSIZE)
    
    # Create a custom grid layout
    gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3,
                         left=0.05, right=0.95, top=0.95, bottom=0.05)
    
    # Top section for title
    ax_title = fig.add_subplot(gs[0, :])
    ax_title.axis('off')
    
    # Left section for initial rows
    ax_initial = fig.add_subplot(gs[1:, 0])
    
    # Right section for bisection tree and final range
    ax_tree = fig.add_subplot(gs[1:, 1])
    
    # === Title Section ===
    ax_title.text(0.5, 0.5, 'ROW RANGE BISECTOR', 
                 ha='center', va='center', fontsize=24, fontweight='bold',
                 family='monospace')
    
    # === Initial Rows Section ===
    ax_initial.set_xlim(0, 10)
    ax_initial.set_ylim(-0.5, 9.5)
    ax_initial.set_aspect('equal')
    ax_initial.axis('off')
    ax_initial.set_title('Initial Rows', fontsize=14, fontweight='bold', pad=20)
    
    num_rows = 9  # Rows 0-8
    row_height = 0.8
    row_spacing = 0.2
    error_rows = [2, 4, 7]  # 0-indexed: rows 2, 4, 7
    
    # Column label "C" at top
    ax_initial.text(5, 9.2, 'C', ha='center', va='bottom',
                   fontsize=14, fontweight='bold')
    
    for i in range(num_rows):
        # Calculate y position from top (row 0 at top)
        y_pos = (num_rows - 1 - i) * (row_height + row_spacing) + 0.5
        is_error = i in error_rows
        
        # Row rectangle - centered horizontally
        rect_x = 5 - 2.5  # Center at x=5, width 5, so start at 2.5
        rect_width = 5.0
        
        if is_error:
            # Error row - pink/red
            rect = Rectangle((rect_x, y_pos - row_height/2), rect_width, row_height,
                           facecolor='#ffb6c1', edgecolor='#333333', linewidth=2)
        else:
            # Normal row
            rect = Rectangle((rect_x, y_pos - row_height/2), rect_width, row_height,
                           facecolor='white', edgecolor='#e0e0e0', linewidth=1.2)
        ax_initial.add_patch(rect)
        
        # Row number label
        ax_initial.text(rect_x - 0.3, y_pos, f'{i}', ha='right', va='center',
                       fontsize=10, fontweight='bold')
        
        # Error mark
        if is_error:
            ax_initial.text(rect_x + rect_width + 0.3, y_pos, '✗', ha='left', va='center',
                          fontsize=12, color='red', fontweight='bold')
    
    # === Bisection Tree Section ===
    ax_tree.set_xlim(0, 10)
    ax_tree.set_ylim(0, 10)
    ax_tree.set_aspect('equal')
    ax_tree.axis('off')
    ax_tree.set_title('Bisection Tree', fontsize=14, fontweight='bold', pad=20)
    
    # Root: All rows [0-9)
    root_x, root_y = 5, 9
    ax_tree.text(root_x, root_y, '[0-9)', ha='center', va='center',
                fontsize=11, fontweight='bold', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#ffcccc', edgecolor='red', linewidth=2))
    ax_tree.text(root_x, root_y - 0.4, '✗ FAIL', ha='center', va='top',
                fontsize=10, color='red', fontweight='bold')
    
    # Level 1: Split into [0-4) and [4-9)
    left1_x, left1_y = 2, 6.5
    right1_x, right1_y = 8, 6.5
    
    # Draw connecting lines
    ax_tree.plot([root_x, left1_x], [root_y - 0.3, left1_y + 0.3], 'k-', linewidth=2, alpha=0.6)
    ax_tree.plot([root_x, right1_x], [root_y - 0.3, right1_y + 0.3], 'k-',
                linewidth=2, alpha=0.6)
    
    # Left child: [0-4) - PASS
    ax_tree.text(left1_x, left1_y, '[0-2)', ha='center', va='center',
                fontsize=11, fontweight='bold', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#ccffcc', edgecolor='green', linewidth=2))
    ax_tree.text(left1_x, left1_y - 0.4, '✓ PASS', ha='center', va='top',
                fontsize=10, color='green', fontweight='bold')
    
    # Right child: [4-9) - FAIL
    ax_tree.text(right1_x, right1_y, '[3-9)', ha='center', va='center',
                fontsize=11, fontweight='bold', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#ffcccc', edgecolor='red', linewidth=2))
    ax_tree.text(right1_x, right1_y - 0.4, '✗ FAIL', ha='center', va='top',
                fontsize=10, color='red', fontweight='bold')
    
    # Level 2: Split [4-9) into [4-6) and [6-9)
    left2_x, left2_y = 6, 4
    right2_x, right2_y = 10, 4
    
    ax_tree.plot([right1_x, left2_x], [right1_y - 0.3, left2_y + 0.3], 'k-', linewidth=2, alpha=0.6)
    ax_tree.plot([right1_x, right2_x], [right1_y - 0.3, right2_y + 0.3], 'k-',
                linewidth=2, alpha=0.6)
    
    
    # [6-9) - FAIL
    ax_tree.text(left2_x, left2_y, '[3-8)', ha='center', va='center',
                fontsize=11, fontweight='bold', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#ffcccc', edgecolor='red', linewidth=2))
    ax_tree.text(left2_x, left2_y - 0.4, '✗ FAIL', ha='center', va='top',
                fontsize=10, color='red', fontweight='bold')

    # [8-9) - PASS
    ax_tree.text(right2_x, right2_y, '[8-9)', ha='center', va='center',
                fontsize=11, fontweight='bold', family='monospace',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#ccffcc', edgecolor='green', linewidth=2))
    ax_tree.text(right2_x, right2_y - 0.4, '✓ PASS', ha='center', va='top',
                fontsize=10, color='green', fontweight='bold')

    
    # Level 3: Combine [0-4) (PASS) + [4-6) (PASS) + [6-9) (FAIL) analysis
    # Need to find minimal failing range [2-8)
    final_x, final_y = 5, 1.5
    ax_tree.text(final_x, final_y, 'Minimal Failing Range: [3-8)', ha='center', va='center',
                fontsize=11, fontweight='bold', family='monospace',
                bbox=dict(boxstyle='round,pad=0.8', facecolor='#ffffcc', edgecolor='orange', linewidth=2))
    
    plt.tight_layout()
    
    if output_path is None:
        output_path = 'row_range_bisector_diagram.png'
    
    plt.savefig(output_path, dpi=dpi, bbox_inches='tight')
    
    if show:
        plt.show()
    else:
        plt.close()


def draw_sampling_row_bisector_diagram(
    output_path: Optional[str] = None,
    dpi: int = DIAGRAM_DPI,
    show: bool = False,
) -> None:
    """
    Draw a classic CS algorithm diagram showing the sampling row bisector algorithm.
    """
    fig = plt.figure(figsize=DIAGRAM_FIGSIZE)
    
    # Create a custom grid layout
    gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3,
                         left=0.05, right=0.95, top=0.95, bottom=0.05)
    
    # Top section for title
    ax_title = fig.add_subplot(gs[0, :])
    ax_title.axis('off')
    
    # Left section for sampling iterations
    ax_samples = fig.add_subplot(gs[1:, 0])
    
    # Right section for final result
    ax_result = fig.add_subplot(gs[1:, 1])
    
    # === Title Section ===
    ax_title.text(0.5, 0.5, 'SAMPLING ROW BISECTOR', 
                 ha='center', va='center', fontsize=24, fontweight='bold',
                 family='monospace')
    
    # === Sampling Iterations Section ===
    ax_samples.set_xlim(0, 10)
    ax_samples.set_ylim(0, 10)
    ax_samples.set_aspect('equal')
    ax_samples.axis('off')
    ax_samples.set_title('Sampling Iterations', fontsize=14, fontweight='bold', pad=20)
    
    # Initial range
    ax_samples.text(5, 8.5, 'Initial Range: [2-7]', ha='center', va='center',
                   fontsize=11, fontweight='bold', family='monospace',
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='#ffcccc', edgecolor='red', linewidth=2))
    
    # Iteration 1: Sample [3, 5, 6]
    ax_samples.text(2.5, 6.5, 'Iteration 1:', ha='left', va='center',
                   fontsize=10, fontweight='bold')
    ax_samples.text(5, 6.5, '[3, 5, 6]', ha='center', va='center',
                   fontsize=10, fontweight='bold', family='monospace',
                   bbox=dict(boxstyle='round,pad=0.4', facecolor='#ccffcc', edgecolor='green', linewidth=2))
    ax_samples.text(7.5, 6.5, '✓ PASS', ha='left', va='center',
                   fontsize=10, color='green', fontweight='bold')
    
    # Iteration 2: Sample [2, 3, 4, 5]
    ax_samples.text(2.5, 5, 'Iteration 2:', ha='left', va='center',
                   fontsize=10, fontweight='bold')
    ax_samples.text(5, 5, '[2, 3, 4, 5]', ha='center', va='center',
                   fontsize=10, fontweight='bold', family='monospace',
                   bbox=dict(boxstyle='round,pad=0.4', facecolor='#ffcccc', edgecolor='red', linewidth=2))
    ax_samples.text(7.5, 5, '✗ FAIL', ha='left', va='center',
                   fontsize=10, color='red', fontweight='bold')
    
    # Iteration 3: Sample [2, 4, 6, 7]
    ax_samples.text(2.5, 3.5, 'Iteration 3:', ha='left', va='center',
                   fontsize=10, fontweight='bold')
    ax_samples.text(5, 3.5, '[2, 4, 6, 7]', ha='center', va='center',
                   fontsize=10, fontweight='bold', family='monospace',
                   bbox=dict(boxstyle='round,pad=0.4', facecolor='#ffcccc', edgecolor='red', linewidth=2))
    ax_samples.text(7.5, 3.5, '✗ FAIL', ha='left', va='center',
                   fontsize=10, color='red', fontweight='bold')
    
    # === Final Result Section ===
    ax_result.set_xlim(0, 10)
    ax_result.set_ylim(0, 10)
    ax_result.set_aspect('equal')
    ax_result.axis('off')
    ax_result.set_title('Minimal Failing Set', fontsize=14, fontweight='bold', pad=20)
    
    # Final minimal set
    ax_result.text(5, 7, 'Minimal Failing Set:', ha='center', va='center',
                  fontsize=12, fontweight='bold')
    
    ax_result.text(5, 5, '{2, 4, 7}', ha='center', va='center',
                  fontsize=14, fontweight='bold', family='monospace',
                  bbox=dict(boxstyle='round,pad=0.8', facecolor='#ffffcc', edgecolor='orange', linewidth=2))
    
    # Show individual rows
    error_rows = [2, 4, 7]
    row_height = 0.6
    for i, row in enumerate(error_rows):
        y = 3 - i * row_height
        rect = Rectangle((3, y - 0.25), 4, 0.5,
                        facecolor='#ffb6c1', edgecolor='#333333', linewidth=2)
        ax_result.add_patch(rect)
        ax_result.text(5, y, f'Row {row}', ha='center', va='center',
                      fontsize=11, fontweight='bold')
        ax_result.text(7, y, '✗', ha='center', va='center',
                      fontsize=12, color='red', fontweight='bold')
    
    plt.tight_layout()
    
    if output_path is None:
        output_path = 'sampling_row_bisector_diagram.png'
    
    plt.savefig(output_path, dpi=dpi, bbox_inches='tight')
    
    if show:
        plt.close()


def _draw_s_curved_arrow(ax, x_start, y_start, x_end, y_end, dip_amount=0.4, horizontal_offset=0.0):
    """
    Draw an S-shaped arrow (rotated 90 degrees) with:
    - Tail pointing straight down from column box
    - Smooth S-curve in the middle (like a rotated S)
    - Head pointing straight down at exec box
    - Horizontal offset to prevent arrows from crossing
    """
    import numpy as np
    
    # Apply horizontal offset to prevent arrows from crossing
    x_start = x_start + horizontal_offset
    x_end = x_end + horizontal_offset
    
    # Calculate vertical distance
    vertical_dist = y_start - y_end
    
    # Start with a short straight segment pointing down
    tail_length = min(0.12, vertical_dist * 0.08)
    tail_end_y = y_start - tail_length
    
    # Calculate the inflection point (middle of S-curve)
    mid_y = (tail_end_y + y_end) / 2
    
    # Calculate horizontal distance and determine curve direction
    horizontal_dist = x_end - x_start
    # Base curve magnitude on horizontal distance, with minimum for visibility
    base_curve = max(abs(horizontal_dist) * 0.5, 0.3)
    curve_magnitude = base_curve + dip_amount * 0.5
    
    # Create smooth S-curve using two cubic bezier curves
    # First half: curve away from start direction (first part of S)
    # Second half: curve back toward end (second part of S)
    
    # Determine which direction to curve first
    if horizontal_dist > 0:
        # Going right - curve left first (away), then back right
        curve_direction = -1
    elif horizontal_dist < 0:
        # Going left - curve right first (away), then back left
        curve_direction = 1
    else:
        # Straight down - use a small curve for visibility
        curve_direction = 1
        horizontal_dist = 0.1
    
    # Control points for first curve (from tail_end to mid_y)
    # This creates the first curve of the S (curving away)
    cp1_x = x_start + curve_direction * curve_magnitude * 0.3
    cp1_y = tail_end_y - (mid_y - tail_end_y) * 0.25
    
    cp2_x = x_start + curve_direction * curve_magnitude * 0.6
    cp2_y = mid_y - (mid_y - tail_end_y) * 0.15
    
    # Inflection point (middle of S)
    inflection_x = x_start + horizontal_dist * 0.5 + curve_direction * curve_magnitude * 0.2
    
    # Control points for second curve (from mid_y to y_end)
    # This creates the second curve of the S (curving back, ending straight down)
    cp3_x = x_end - curve_direction * curve_magnitude * 0.3
    cp3_y = mid_y + (y_end - mid_y) * 0.15
    
    # cp4 ensures the curve ends pointing straight down
    cp4_x = x_end
    cp4_y = y_end + (y_end - mid_y) * 0.25
    
    # Create the path: straight tail, then smooth S-curve
    verts = [
        (x_start, y_start),      # Start point
        (x_start, tail_end_y),   # End of straight tail
        (cp1_x, cp1_y),          # Control point 1 for first curve
        (cp2_x, cp2_y),          # Control point 2 for first curve
        (inflection_x, mid_y),   # Inflection point (middle of S)
        (cp3_x, cp3_y),          # Control point 1 for second curve
        (cp4_x, cp4_y),          # Control point 2 for second curve (ensures straight down)
        (x_end, y_end),          # End point
    ]
    codes = [
        Path.MOVETO,
        Path.LINETO,  # Straight tail down
        Path.CURVE4, Path.CURVE4, Path.CURVE4,  # First cubic bezier (curves away)
        Path.CURVE4, Path.CURVE4, Path.CURVE4,  # Second cubic bezier (curves back, pointing down)
    ]
    
    path = Path(verts, codes)
    patch = PathPatch(path, edgecolor='#666', facecolor='none', 
                     linewidth=2.5, alpha=0.8)
    ax.add_patch(patch)
    
    # Add arrowhead pointing straight down
    arrow_len = 0.18
    arrow_width = 0.1
    tip_x, tip_y = x_end, y_end
    left_x = tip_x - arrow_width
    left_y = tip_y + arrow_len
    right_x = tip_x + arrow_width
    right_y = tip_y + arrow_len
    
    arrow_path = Path([(left_x, left_y), (tip_x, tip_y), (right_x, right_y), (left_x, left_y)],
                     [Path.MOVETO, Path.LINETO, Path.LINETO, Path.CLOSEPOLY])
    arrow_patch = PathPatch(arrow_path, facecolor='#666', edgecolor='#666', 
                           linewidth=2.5, alpha=0.8)
    ax.add_patch(arrow_patch)


def draw_execution_strategy_diagram(
    output_path: Optional[str] = None,
    dpi: int = DIAGRAM_DPI,
    show: bool = False,
) -> None:
    """
    Draw a diagram showing the column execution planning strategy.
    
    Shows the progression of column processing with working groups,
    backoff strategies, and summary stats accumulation.
    """
    fig = plt.figure(figsize=EXECUTION_STRATEGY_FIGSIZE)
    
    ax = fig.add_subplot(111)
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 10)
    ax.axis('off')
    ax.set_title('EXECUTION STRATEGY', fontsize=20, fontweight='bold', pad=20, family='monospace')
    
    # Layout variables - change these to adjust spacing consistently
    col_col_x = 0.5
    exec_col_x = 5.5
    cell_width = 4.5
    cell_height = 0.7
    border_width = 2
    
    num_cols = 9  # Number of column boxes to show
    box_width = 0.35
    box_height = 0.35
    box_spacing = 0.05  # Spacing between column boxes
    exec_box_spacing = 0.2  # Spacing between exec boxes
    
    # Arrow positioning variables
    arrow_dip_amount = 0.4  # How much the arrow dips/swings for S-shape
    
    # Draw header borders first
    header_y = 9.2
    header_height = 0.3
    header_center_y = header_y + header_height/2
    # COLUMNS header
    ax.add_patch(Rectangle((col_col_x, header_y), cell_width, header_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    # EXEC header
    ax.add_patch(Rectangle((exec_col_x, header_y), cell_width, header_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    
    # Column headers (centered in header boxes)
    ax.text(col_col_x + cell_width/2, header_center_y, 'COLUMNS', ha='center', va='center', fontsize=14, fontweight='bold')
    ax.text(exec_col_x + cell_width/2, header_center_y, 'EXEC', ha='center', va='center', fontsize=14, fontweight='bold')
    
    # Row A: Initial state
    row_letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M']
    # Adjust row spacing to fit all rows within ylim(0, 10)
    # Header at 9.5, 13 rows, so spacing = (9.0 - 0.5) / 13 ≈ 0.65
    row_spacing = 0.65
    row1_y = 8.5
    row1_idx = 0
    
    # Draw cell borders
    cell_y = row1_y - cell_height/2
    # COLUMNS cell
    ax.add_patch(Rectangle((col_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    # Diagram in COLUMNS cell
    col_start_x = col_col_x + 0.3
    for i in range(num_cols):
        x = col_start_x + i * (box_width + box_spacing)
        rect = Rectangle((x, row1_y - box_height/2), box_width, box_height,
                        facecolor='white', edgecolor='#ccc', linewidth=1)
        ax.add_patch(rect)
    
    # EXEC cell
    ax.add_patch(Rectangle((exec_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    # Text in EXEC cell
    ax.text(exec_col_x + 0.3, row1_y, 'initial column state,\nno summary stats', 
           ha='left', va='center', fontsize=10, family='monospace')
    
    # Row B: First execution - text in COLUMNS, exec diagram in EXEC
    row2_y = row1_y - row_spacing
    row2_idx = 1
    cell_y = row2_y - cell_height/2
    
    # COLUMNS cell - text explaining
    ax.add_patch(Rectangle((col_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    ax.text(col_col_x + 0.3, row2_y, 'First execution', ha='left', va='center', 
           fontsize=11, family='monospace', fontweight='bold')
    
    # EXEC cell - diagram
    ax.add_patch(Rectangle((exec_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    # Exec diagram - 1 box with checkmark
    exec_x = exec_col_x + 0.3
    rect = Rectangle((exec_x, row2_y - box_height/2), box_width, box_height,
                    facecolor='white', edgecolor='#333', linewidth=2)
    ax.add_patch(rect)
    ax.text(exec_x + box_width/2, row2_y, '1', ha='center', va='center', fontsize=9, fontweight='bold')
    ax.text(exec_x + box_width + 0.1, row2_y, '✓', ha='left', va='center', fontsize=18, color='green', fontweight='bold')
    
    # Draw S-curved arrow from first row columns to first exec box (row B)
    arrow_y_start = row1_y + box_height/2  # Start from top of column box
    arrow_y_end = row2_y + box_height/2  # End at top of exec box
    x_start = col_start_x + box_width/2  # Center of first column box
    x_end = exec_x + box_width/2  # Center of first exec box
    _draw_s_curved_arrow(ax, x_start, arrow_y_start, x_end, arrow_y_end, arrow_dip_amount)
    
    # Row C: Columns diagram in COLUMNS, text in EXEC
    row3_y = row2_y - row_spacing
    row3_idx = 2
    cell_y = row3_y - cell_height/2
    
    # COLUMNS cell - diagram
    ax.add_patch(Rectangle((col_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    # Columns diagram - 1 blue box, 8 empty
    x = col_start_x
    rect = Rectangle((x, row3_y - box_height/2), box_width, box_height,
                    facecolor='#b3d9ff', edgecolor='#333', linewidth=1.5)
    ax.add_patch(rect)
    ax.text(x + box_width/2, row3_y, '1', ha='center', va='center', fontsize=9, fontweight='bold')
    
    # 8 empty boxes
    for i in range(1, num_cols):
        x = col_start_x + i * (box_width + box_spacing)
        rect = Rectangle((x, row3_y - box_height/2), box_width, box_height,
                        facecolor='white', edgecolor='#ccc', linewidth=1)
        ax.add_patch(rect)
    
    # EXEC cell - text
    ax.add_patch(Rectangle((exec_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    ax.text(exec_col_x + 0.3, row3_y, '1 successful summary\nstat col added', 
           ha='left', va='center', fontsize=10, family='monospace')
    
    # Row D: Text in COLUMNS, exec diagram in EXEC
    row4_y = row3_y - row_spacing
    row4_idx = 3
    cell_y = row4_y - cell_height/2
    
    # COLUMNS cell - text
    ax.add_patch(Rectangle((col_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    ax.text(col_col_x + 0.3, row4_y, '2x working group', ha='left', va='center', 
           fontsize=11, color='#d32f2f', fontweight='bold', family='monospace')
    
    # EXEC cell - diagram
    ax.add_patch(Rectangle((exec_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    # Exec diagram - 2 boxes with checkmarks
    exec_box_positions = []
    for i in range(2):
        x_pos = exec_x + i * (box_width + exec_box_spacing)
        exec_box_positions.append(x_pos)
        rect = Rectangle((x_pos, row4_y - box_height/2), box_width, box_height,
                        facecolor='white', edgecolor='#333', linewidth=2)
        ax.add_patch(rect)
        ax.text(x_pos + box_width/2, row4_y, '2', ha='center', va='center', fontsize=9, fontweight='bold')
        ax.text(x_pos + box_width + 0.1, row4_y, '✓', ha='left', va='center', fontsize=18, color='green', fontweight='bold')
    
    # Draw S-curved arrows from column boxes 2 and 3 in row 3 to exec boxes in row 4
    arrow_y_start = row3_y + box_height/2  # Start from top of column boxes
    arrow_y_end = row4_y + box_height/2  # End at top of exec boxes
    arrow_h_spacing = 0.25  # Horizontal spacing to prevent crossing
    for box_idx, col_idx in enumerate([1, 2]):  # boxes 2 and 3 (0-indexed: 1, 2)
        x_start = col_start_x + col_idx * (box_width + box_spacing) + box_width/2
        x_end = exec_box_positions[box_idx] + box_width/2  # Center of exec box
        horizontal_offset = (box_idx - 0.5) * arrow_h_spacing  # Offset to prevent crossing
        _draw_s_curved_arrow(ax, x_start, arrow_y_start, x_end, arrow_y_end, arrow_dip_amount, horizontal_offset)
    
    # Row E: Columns diagram in COLUMNS, text in EXEC
    row5_y = row4_y - row_spacing
    row5_idx = 4
    cell_y = row5_y - cell_height/2
    
    # COLUMNS cell - diagram
    ax.add_patch(Rectangle((col_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    # Columns diagram - 3 blue boxes, 5 empty
    for i in range(3):
        x = col_start_x + i * (box_width + box_spacing)
        rect = Rectangle((x, row5_y - box_height/2), box_width, box_height,
                        facecolor='#b3d9ff', edgecolor='#333', linewidth=1.5)
        ax.add_patch(rect)
        ax.text(x + box_width/2, row5_y, str(i+1), ha='center', va='center', fontsize=9, fontweight='bold')
    
    for i in range(3, num_cols):
        x = col_start_x + i * (box_width + box_spacing)
        rect = Rectangle((x, row5_y - box_height/2), box_width, box_height,
                        facecolor='white', edgecolor='#ccc', linewidth=1)
        ax.add_patch(rect)
    
    # EXEC cell - text
    ax.add_patch(Rectangle((exec_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    ax.text(exec_col_x + 0.3, row5_y, '2 successful summary\nstats added', 
           ha='left', va='center', fontsize=10, family='monospace')
    
    # Row F: Text in COLUMNS, exec diagram in EXEC
    row6_y = row5_y - row_spacing
    row6_idx = 5
    cell_y = row6_y - cell_height/2
    
    # COLUMNS cell - text
    ax.add_patch(Rectangle((col_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    ax.text(col_col_x + 0.3, row6_y, '2x working group', ha='left', va='center', 
           fontsize=11, color='#d32f2f', fontweight='bold', family='monospace')
    
    # EXEC cell - diagram
    ax.add_patch(Rectangle((exec_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    # Exec diagram - 4 boxes with red X
    exec_box_positions = []
    for i in range(4):
        x_pos = exec_x + i * (box_width + exec_box_spacing)
        exec_box_positions.append(x_pos)
        rect = Rectangle((x_pos, row6_y - box_height/2), box_width, box_height,
                        facecolor='white', edgecolor='#333', linewidth=2)
        ax.add_patch(rect)
        ax.text(x_pos + box_width/2, row6_y, str(i+1), ha='center', va='center', fontsize=9, fontweight='bold')
        ax.text(x_pos + box_width + 0.1, row6_y, '✗', ha='left', va='center', fontsize=12, color='red', fontweight='bold')
    
    # Draw S-curved arrows from column boxes 4,5,6,7 in row 5 to exec boxes in row 6
    arrow_y_start = row5_y + box_height/2  # Start from top of column boxes
    arrow_y_end = row6_y + box_height/2  # End at top of exec boxes
    arrow_h_spacing = 0.22  # Horizontal spacing to prevent crossing
    for box_idx, col_idx in enumerate([3, 4, 5, 6]):  # boxes 4,5,6,7 (0-indexed: 3,4,5,6)
        x_start = col_start_x + col_idx * (box_width + box_spacing) + box_width/2
        x_end = exec_box_positions[box_idx] + box_width/2  # Center of exec box
        horizontal_offset = (box_idx - 1.5) * arrow_h_spacing  # Offset to prevent crossing (centered)
        _draw_s_curved_arrow(ax, x_start, arrow_y_start, x_end, arrow_y_end, arrow_dip_amount, horizontal_offset)
    
    # Row G: Columns diagram in COLUMNS, text in EXEC
    row7_y = row6_y - row_spacing
    row7_idx = 6
    cell_y = row7_y - cell_height/2
    
    # COLUMNS cell - diagram
    ax.add_patch(Rectangle((col_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    # Columns diagram - 3 blue boxes, 5 empty
    for i in range(3):
        x = col_start_x + i * (box_width + box_spacing)
        rect = Rectangle((x, row7_y - box_height/2), box_width, box_height,
                        facecolor='#b3d9ff', edgecolor='#333', linewidth=1.5)
        ax.add_patch(rect)
        ax.text(x + box_width/2, row7_y, str(i+1), ha='center', va='center', fontsize=9, fontweight='bold')
    
    for i in range(3, num_cols):
        x = col_start_x + i * (box_width + box_spacing)
        rect = Rectangle((x, row7_y - box_height/2), box_width, box_height,
                        facecolor='white', edgecolor='#ccc', linewidth=1)
        ax.add_patch(rect)
    
    # EXEC cell - text
    ax.add_patch(Rectangle((exec_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    ax.text(exec_col_x + 0.3, row7_y, 'no successful summary\nstats added', 
           ha='left', va='center', fontsize=10, family='monospace')
    
    # Row H: Text in COLUMNS, exec diagram in EXEC
    row8_y = row7_y - row_spacing
    row8_idx = 7
    cell_y = row8_y - cell_height/2
    
    # COLUMNS cell - text
    ax.add_patch(Rectangle((col_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    ax.text(col_col_x + 0.3, row8_y, 'backoff working\ngroup size', ha='left', va='center', 
           fontsize=11, color='#d32f2f', fontweight='bold', family='monospace')
    
    # EXEC cell - diagram
    ax.add_patch(Rectangle((exec_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    # Exec diagram - 2 boxes with green checkmarks
    exec_box_positions = []
    for i in range(2):
        x_pos = exec_x + i * (box_width + exec_box_spacing)
        exec_box_positions.append(x_pos)
        rect = Rectangle((x_pos, row8_y - box_height/2), box_width, box_height,
                        facecolor='white', edgecolor='#333', linewidth=2)
        ax.add_patch(rect)
        ax.text(x_pos + box_width/2, row8_y, str(i+1), ha='center', va='center', fontsize=9, fontweight='bold')
        ax.text(x_pos + box_width + 0.1, row8_y, '✓', ha='left', va='center', fontsize=18, color='green', fontweight='bold')
    
    # Draw S-curved arrows from column boxes 4,5 in row 7 to exec boxes in row 8
    arrow_y_start = row7_y + box_height/2  # Start from top of column boxes
    arrow_y_end = row8_y + box_height/2  # End at top of exec boxes
    arrow_h_spacing = 0.25  # Horizontal spacing to prevent crossing
    for box_idx, col_idx in enumerate([3, 4]):  # boxes 4,5 (0-indexed: 3,4)
        x_start = col_start_x + col_idx * (box_width + box_spacing) + box_width/2
        x_end = exec_box_positions[box_idx] + box_width/2  # Center of exec box
        horizontal_offset = (box_idx - 0.5) * arrow_h_spacing  # Offset to prevent crossing
        _draw_s_curved_arrow(ax, x_start, arrow_y_start, x_end, arrow_y_end, arrow_dip_amount, horizontal_offset)
    
    # Row I: Columns diagram in COLUMNS, text in EXEC
    row9_y = row8_y - row_spacing
    row9_idx = 8
    cell_y = row9_y - cell_height/2
    
    # COLUMNS cell - diagram
    ax.add_patch(Rectangle((col_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    # Columns diagram - 5 blue boxes, 4 empty
    for i in range(5):
        x = col_start_x + i * (box_width + box_spacing)
        rect = Rectangle((x, row9_y - box_height/2), box_width, box_height,
                        facecolor='#b3d9ff', edgecolor='#333', linewidth=1.5)
        ax.add_patch(rect)
        ax.text(x + box_width/2, row9_y, str(i+1), ha='center', va='center', fontsize=9, fontweight='bold')
    
    for i in range(5, num_cols):
        x = col_start_x + i * (box_width + box_spacing)
        rect = Rectangle((x, row9_y - box_height/2), box_width, box_height,
                        facecolor='white', edgecolor='#ccc', linewidth=1)
        ax.add_patch(rect)
    
    # EXEC cell - text
    ax.add_patch(Rectangle((exec_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    ax.text(exec_col_x + 0.3, row9_y, '2 columns added', 
           ha='left', va='center', fontsize=10, family='monospace')
    
    # Row J: Text in COLUMNS, exec diagram in EXEC
    row10_y = row9_y - row_spacing
    row10_idx = 9
    cell_y = row10_y - cell_height/2
    
    # COLUMNS cell - text
    ax.add_patch(Rectangle((col_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    ax.text(col_col_x + 0.3, row10_y, '2x working group', ha='left', va='center', 
           fontsize=11, color='#d32f2f', fontweight='bold', family='monospace')
    
    # EXEC cell - diagram
    ax.add_patch(Rectangle((exec_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    # Exec diagram - 2 boxes with checkmarks
    exec_box_positions = []
    for i in range(2):
        x_pos = exec_x + i * (box_width + exec_box_spacing)
        exec_box_positions.append(x_pos)
        rect = Rectangle((x_pos, row10_y - box_height/2), box_width, box_height,
                        facecolor='white', edgecolor='#333', linewidth=2)
        ax.add_patch(rect)
        ax.text(x_pos + box_width/2, row10_y, str(i+1), ha='center', va='center', fontsize=9, fontweight='bold')
        ax.text(x_pos + box_width + 0.1, row10_y, '✓', ha='left', va='center', fontsize=18, color='green', fontweight='bold')
    
    # Draw S-curved arrows from column boxes 6,7 in row 9 to exec boxes in row 10
    arrow_y_start = row9_y + box_height/2  # Start from top of column boxes
    arrow_y_end = row10_y + box_height/2  # End at top of exec boxes
    arrow_h_spacing = 0.25  # Horizontal spacing to prevent crossing
    for box_idx, col_idx in enumerate([5, 6]):  # boxes 6,7 (0-indexed: 5,6)
        x_start = col_start_x + col_idx * (box_width + box_spacing) + box_width/2
        x_end = exec_box_positions[box_idx] + box_width/2  # Center of exec box
        horizontal_offset = (box_idx - 0.5) * arrow_h_spacing  # Offset to prevent crossing
        _draw_s_curved_arrow(ax, x_start, arrow_y_start, x_end, arrow_y_end, arrow_dip_amount, horizontal_offset)
    
    # Row K: Columns diagram in COLUMNS, text in EXEC
    row11_y = row10_y - row_spacing
    row11_idx = 10
    cell_y = row11_y - cell_height/2
    
    # COLUMNS cell - diagram
    ax.add_patch(Rectangle((col_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    # Columns diagram - 7 blue boxes, 2 empty
    for i in range(7):
        x = col_start_x + i * (box_width + box_spacing)
        rect = Rectangle((x, row11_y - box_height/2), box_width, box_height,
                        facecolor='#b3d9ff', edgecolor='#333', linewidth=1.5)
        ax.add_patch(rect)
        ax.text(x + box_width/2, row11_y, str(i+1), ha='center', va='center', fontsize=9, fontweight='bold')
    
    for i in range(7, num_cols):
        x = col_start_x + i * (box_width + box_spacing)
        rect = Rectangle((x, row11_y - box_height/2), box_width, box_height,
                        facecolor='white', edgecolor='#ccc', linewidth=1)
        ax.add_patch(rect)
    
    # EXEC cell - text
    ax.add_patch(Rectangle((exec_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    ax.text(exec_col_x + 0.3, row11_y, 'maintain', 
           ha='left', va='center', fontsize=10, family='monospace')
    
    # Row L: Text in COLUMNS, exec diagram in EXEC
    row12_y = row11_y - row_spacing
    row12_idx = 11
    cell_y = row12_y - cell_height/2
    
    # COLUMNS cell - text
    ax.add_patch(Rectangle((col_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    ax.text(col_col_x + 0.3, row12_y, '2x working group', ha='left', va='center', 
           fontsize=11, color='#d32f2f', fontweight='bold', family='monospace')
    
    # EXEC cell - diagram
    ax.add_patch(Rectangle((exec_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    # Exec diagram - 2 boxes with checkmarks
    exec_box_positions = []
    for i in range(2):
        x_pos = exec_x + i * (box_width + exec_box_spacing)
        exec_box_positions.append(x_pos)
        rect = Rectangle((x_pos, row12_y - box_height/2), box_width, box_height,
                        facecolor='white', edgecolor='#333', linewidth=2)
        ax.add_patch(rect)
        ax.text(x_pos + box_width/2, row12_y, str(i+1), ha='center', va='center', fontsize=9, fontweight='bold')
        ax.text(x_pos + box_width + 0.1, row12_y, '✓', ha='left', va='center', fontsize=18, color='green', fontweight='bold')
    
    # Draw S-curved arrows from column boxes 8,9 in row 11 to exec boxes in row 12
    arrow_y_start = row11_y + box_height/2  # Start from top of column boxes
    arrow_y_end = row12_y + box_height/2  # End at top of exec boxes
    arrow_h_spacing = 0.25  # Horizontal spacing to prevent crossing
    for box_idx, col_idx in enumerate([7, 8]):  # boxes 8,9 (0-indexed: 7,8)
        x_start = col_start_x + col_idx * (box_width + box_spacing) + box_width/2
        x_end = exec_box_positions[box_idx] + box_width/2  # Center of exec box
        horizontal_offset = (box_idx - 0.5) * arrow_h_spacing  # Offset to prevent crossing
        _draw_s_curved_arrow(ax, x_start, arrow_y_start, x_end, arrow_y_end, arrow_dip_amount, horizontal_offset)
    
    # Row M: Columns diagram in COLUMNS, text in EXEC (final state)
    row13_y = row12_y - row_spacing
    row13_idx = 12
    cell_y = row13_y - cell_height/2
    
    # COLUMNS cell - diagram
    ax.add_patch(Rectangle((col_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    # Columns diagram - all 9 blue boxes (complete)
    for i in range(9):
        x = col_start_x + i * (box_width + box_spacing)
        rect = Rectangle((x, row13_y - box_height/2), box_width, box_height,
                        facecolor='#b3d9ff', edgecolor='#333', linewidth=1.5)
        ax.add_patch(rect)
        ax.text(x + box_width/2, row13_y, str(i+1), ha='center', va='center', fontsize=9, fontweight='bold')
    
    # EXEC cell - text
    ax.add_patch(Rectangle((exec_col_x, cell_y), cell_width, cell_height,
                          fill=False, edgecolor='black', linewidth=border_width))
    ax.text(exec_col_x + 0.3, row13_y, 'all columns complete', 
           ha='left', va='center', fontsize=10, family='monospace')
    
    plt.tight_layout()
    
    if output_path is None:
        output_path = 'execution_strategy_diagram.png'
    
    plt.savefig(output_path, dpi=dpi, bbox_inches='tight')
    
    if show:
        plt.show()
    else:
        plt.close()


if __name__ == '__main__':
    draw_column_bisector_diagram('column_bisector_diagram.png', show=False)
    print("Diagram saved to column_bisector_diagram.png")
    
    draw_expression_bisector_diagram('expression_bisector_diagram.png', show=False)
    print("Diagram saved to expression_bisector_diagram.png")
    
    draw_row_range_bisector_diagram('row_range_bisector_diagram.png', show=False)
    print("Diagram saved to row_range_bisector_diagram.png")
    
    draw_sampling_row_bisector_diagram('sampling_row_bisector_diagram.png', show=False)
    print("Diagram saved to sampling_row_bisector_diagram.png")
    
    draw_execution_strategy_diagram('execution_strategy_diagram.png', show=False)
    print("Diagram saved to execution_strategy_diagram.png")
