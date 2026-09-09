import pandas as pd
import numpy as np

def excel_extractor(file_path: str) -> str:
    """Reads heterogeneous Excel sheets natively without dropping context headers."""
    try:
        print(f"Attempting to read Excel file: {file_path}")
        excel_data = pd.read_excel(file_path, sheet_name=None)
        full_text = []

        for sheet_name, df in excel_data.items():
            full_text.append(f"=== SHEET: {sheet_name} ===")

            # 1. Deterministically replace tabular hyphens with numeric zeros
            df = df.replace(r'^\s*-\s*$', '0', regex=True)

            # 2. Dynamically search for 'Cleaning' and 'Lab. Cost' anywhere in the file
            cleaning_col = None
            lab_cost_col = None
            header_row_idx = None

            for row_idx, row in df.iterrows():
                row_strs = [str(x).strip().lower() for x in row.values]
                if 'cleaning' in row_strs and ('lab. cost' in row_strs or 'lab cost' in row_strs):
                    cleaning_col = row_strs.index('cleaning')
                    try:
                        lab_cost_col = row_strs.index('lab. cost')
                    except ValueError:
                        lab_cost_col = row_strs.index('lab cost')
                    header_row_idx = row_idx
                    break

            # 3. Merge 'Cleaning' into 'Lab. Cost' ONLY if the standard English format is detected
            if header_row_idx is not None:
                for i in range(header_row_idx + 1, len(df)):
                    try:
                        c_val = float(df.iat[i, cleaning_col]) if pd.notnull(df.iat[i, cleaning_col]) and str(df.iat[i, cleaning_col]).strip() != '' else 0.0
                    except:
                        c_val = 0.0

                    try:
                        l_val = float(df.iat[i, lab_cost_col]) if pd.notnull(df.iat[i, lab_cost_col]) and str(df.iat[i, lab_cost_col]).strip() != '' else 0.0
                    except:
                        l_val = 0.0

                    if c_val > 0:
                        df.iat[i, lab_cost_col] = l_val + c_val
                        df.iat[i, cleaning_col] = np.nan # Hide cleaning value from LLM

            # 4. Drop completely blank rows/columns to save LLM tokens, preserving metadata
            df_clean = df.dropna(how='all', axis=0).dropna(how='all', axis=1)

            # 5. Output raw grid without forcing index formatting
            full_text.append(df_clean.to_csv(index=False, header=False))
            full_text.append("=== END SHEET ===\n")

        final_text = "\n".join(full_text)
        print(f"SUCCESS: Extracted {len(final_text)} characters from {file_path}")

        return final_text

    except Exception as e:
        print(f"CRITICAL ERROR extracting text from {file_path}: {e}")
        return ""