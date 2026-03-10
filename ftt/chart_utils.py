from __future__ import annotations


def build_python_script(table_text: str) -> str:
    cleaned = table_text.strip().replace("'''", "''\"")
    lines = [
        "# Auto-generated from DePlot output",
        "import io",
        "import pandas as pd",
        "",
        "table = '''" + cleaned + "'''",
        "# DePlot outputs a pipe-delimited table. Adjust delimiter if needed.",
        "df = pd.read_csv(io.StringIO(table), sep='|', engine='python')",
        "df.columns = [c.strip() for c in df.columns]",
        "print(df)",
    ]
    return "\n".join(lines)
