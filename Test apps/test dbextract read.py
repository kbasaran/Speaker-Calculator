import pandas as pd

file = "./data_Frequency Response_Frequency Response.txt"

with open(file, mode="rt") as extract_file:
    lines = extract_file.read().splitlines()
    """Read a Klippel dB extract export .txt file."""
    if lines[0] == "XY_data" and lines[1][:4] == "DUTs":
        extract_file.seek(0, 0)
        data = pd.read_csv(extract_file,
                           delimiter=",",
                           header=1,
                           index_col="DUTs",
                           encoding='unicode_escape',
                           )
        data.columns = [float(i) for i in data.columns]

data.info()

for row in data.iterrows():
    print(row.index)
    