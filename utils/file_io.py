# This file is part of Speaker Calculator - Loudspeaker design and calculations tool
# Copyright (C) 2026 - Kerem Basaran
# https://github.com/kbasaran
__email__ = "kbasaran@gmail.com"

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from pathlib import Path
from core.models import Wire
import pandas as pd



def read_wire_table(wire_table_file: Path) -> pd.DataFrame:
    if not wire_table_file.exists():
        raise FileNotFoundError(f"Wire table file not found: {wire_table_file}")

    imported_wire_table = pd.read_excel(wire_table_file, "Sheet1", skiprows=range(2), index_col=0)
    coeff_for_SI = {
        "nominal_size": 1e-6,
        "w_avg": 1e-6,
        "h_avg": 1e-6,
        "w_max": 1e-6,
        "nominal_size": 1e-6,
        "mass_density": 1e-3,
    }
    for key, coeff in coeff_for_SI.items():
        imported_wire_table[key] = coeff * imported_wire_table[key]
    if not imported_wire_table.index.is_unique:
        raise IndexError("Wire names in the imported table are not unique.")

    wires_as_dict = dict()
    for wire_name, columns_data_as_series in imported_wire_table.iterrows():
        wires_as_dict[wire_name] = Wire(name=wire_name, **columns_data_as_series.to_dict())

    return wires_as_dict