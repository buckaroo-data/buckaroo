"""
Utility functions for reading files into Polars LazyFrames.
"""
# state:READONLY

from __future__ import annotations

from pathlib import Path
from typing import Optional, Any


def read_df(file_path: str | Path, **kwargs): # -> "pl.LazyFrame":
    """
    Read a file (CSV, Parquet, Avro, JSON) into a Polars LazyFrame.
    
    Automatically detects the file format based on the file extension and
    tries appropriate readers in order if the first fails.
    
    Args:
        file_path: Path to the file to read
        **kwargs: Additional arguments passed to the appropriate reader
        
    Returns:
        A Polars LazyFrame
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the file format cannot be determined or read
        
    Examples:
        >>> ldf = buckaroo.read("data.csv")
        >>> ldf = buckaroo.read("data.parquet")
        >>> ldf = buckaroo.read("data.json")
    """
    #keep polars out of module level imports so that polars cna be an optional dependency
    import polars as pl # noqa: F401
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    extension = file_path.suffix.lower()
    
    # Try readers based on extension, with fallbacks
    readers = []
    
    if extension == '.csv':
        readers = [
            ('csv', lambda: pl.scan_csv(file_path, **kwargs)),
        ]
    elif extension == '.tsv':
        readers = [
            ('csv', lambda: pl.scan_csv(file_path, separator="\t", **kwargs)),
        ]
    elif extension == '.parquet':
        readers = [
            ('parquet', lambda: pl.scan_parquet(file_path, **kwargs)),
        ]
    elif extension == '.avro':
        readers = [
            ('avro', lambda: pl.scan_ipc(file_path, **kwargs)),
            ('avro (as parquet)', lambda: pl.scan_parquet(file_path, **kwargs)),
        ]
    elif extension in ['.json', '.jsonl', '.ndjson']:
        # Try JSON first, then JSONL
        readers = [
            ('json', lambda: pl.scan_ndjson(file_path, **kwargs)),
            ('json (as json)', lambda: pl.read_json(file_path, **kwargs).lazy()),
        ]
    elif extension == '.ipc' or extension == '.arrow':
        readers = [
            ('ipc', lambda: pl.scan_ipc(file_path, **kwargs)),
        ]
    else:
        # Try common formats in order
        readers = [
            ('parquet', lambda: pl.scan_parquet(file_path, **kwargs)),
            ('csv', lambda: pl.scan_csv(file_path, **kwargs)),
            ('json', lambda: pl.scan_ndjson(file_path, **kwargs)),
            ('ipc', lambda: pl.scan_ipc(file_path, **kwargs)),
        ]
    
    last_error: Optional[Exception] = None
    
    for reader_name, reader_func in readers:
        try:
            return reader_func()
        except Exception as e:
            last_error = e
            continue
    
    # If all readers failed, raise an informative error
    raise ValueError(
        f"Could not read file {file_path} with any supported format. "
        f"Extension: {extension}. Last error: {last_error}"
    ) from last_error

def read(file_path: str | Path, **kwargs) -> Any:
    from buckaroo.lazy_infinite_polars_widget import LazyInfinitePolarsBuckarooWidget
    ldf = read_df(file_path)
    return LazyInfinitePolarsBuckarooWidget(ldf, file_path=file_path, **kwargs)
