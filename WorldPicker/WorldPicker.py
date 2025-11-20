# Program takes an Archipelago file as an input, and returns the order to start the worlds base on the number of sphere 1 checks.

import zlib
import pickle
import sys
import os
import io

# --- Placeholder Object for Safe Unpickling ---
class PlaceholderObject:
    """
    Captures data from missing classes (like NetUtils.NetworkSlot) during unpickling.
    Handles __new__ arguments (for NamedTuples/Slots) and __setstate__ (for standard classes).
    """
    def __new__(cls, *args, **kwargs):
        # Capture constructor arguments (Critical for NEWOBJ opcode)
        obj = super().__new__(cls)
        obj._new_args = args
        obj._new_kwargs = kwargs
        return obj

    def __init__(self, *args, **kwargs):
        self._init_args = args
        self._init_kwargs = kwargs
        self._state = None
    
    def __getattr__(self, name):
        if name.startswith("__"): raise AttributeError(name)

        # 1. Check _state (Standard Dict or Tuple)
        state = self.__dict__.get("_state")
        if isinstance(state, dict) and name in state: return state[name]
        if isinstance(state, tuple) and len(state) == 2:
            if isinstance(state[0], dict) and name in state[0]: return state[0][name]
            if isinstance(state[1], dict) and name in state[1]: return state[1][name]

        # 2. Check _new_args (Constructor Arguments)
        # Logic specifically for NetworkSlot(name, game, type, group_members)
        new_args = self.__dict__.get("_new_args")
        if new_args and isinstance(new_args, tuple):
            if name == 'name' and len(new_args) >= 1: return new_args[0]
            if name == 'game' and len(new_args) >= 2: return new_args[1]

        raise AttributeError(f"'{self.__class__.__name__}' placeholder has no attribute '{name}'")

    def __repr__(self):
        return f"<{self.__class__.__module__}.{self.__class__.__name__}>"
    
    def __setstate__(self, state):
        self._state = state

class SafeUnpickler(pickle.Unpickler):
    def __init__(self, file, **kwargs):
        super().__init__(file, **kwargs)
        self.known_placeholders = {}
    
    def find_class(self, module, name):
        try:
            return super().find_class(module, name)
        except (ImportError, AttributeError):
            key = (module, name)
            if key not in self.known_placeholders:
                new_class = type(name, (PlaceholderObject,), {
                    "__module__": module
                })
                self.known_placeholders[key] = new_class
            return self.known_placeholders[key]

# --- Helper: Data Resolution ---
def resolve_player_info(slot_obj, slot_id):
    p_name = "Unknown"
    p_game = "Unknown"

    # Strategy 1: Standard Attributes
    if hasattr(slot_obj, 'name') and slot_obj.name: p_name = slot_obj.name
    if hasattr(slot_obj, 'game') and slot_obj.game: p_game = slot_obj.game

    # Strategy 2: __new__ arguments (Likely for NetworkSlot)
    if p_name == "Unknown":
        new_args = getattr(slot_obj, '_new_args', None)
        if new_args and len(new_args) >= 2:
            p_name = new_args[0]
            p_game = new_args[1]

    # Strategy 3: State Dict
    if p_name == "Unknown":
        state = getattr(slot_obj, '_state', None)
        if isinstance(state, dict):
            p_name = state.get('name', p_name)
            p_game = state.get('game', p_game)

    return p_name, p_game

# --- Main Extraction Logic ---
def process_archipelago_file(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found at path: {file_path}")
        return

    print(f"Processing: {file_path}")
    
    try:
        # 1. Read and Decompress
        with open(file_path, 'rb') as f:
            raw_data = f.read()

        if not raw_data:
            print("Error: File is empty.")
            return

        # Verify it looks like an archipelago file (or at least has data)
        print(f"File size: {len(raw_data)} bytes")
        
        # Decompress (Skip 1st byte version header)
        try:
            decompressed_data = zlib.decompress(raw_data[1:])
        except zlib.error:
            print("Zlib decompression failed. Trying to read as raw pickle (in case it was already decompressed)...")
            decompressed_data = raw_data

        # 2. Unpickle
        try:
            file_buffer = io.BytesIO(decompressed_data)
            data = SafeUnpickler(file_buffer).load()
            print("Unpickling successful.")
        except Exception as e:
            print(f"Error unpickling data: {e}")
            return

        if 'spheres' not in data:
            print("Error: 'spheres' key not found in data.")
            return

        # 3. Build Databases
        print("Mapping Location IDs...")
        location_db = {} 
        if 'datapackage' in data:
            for game_name, game_data in data['datapackage'].items():
                if 'location_name_to_id' in game_data:
                    name_to_id = game_data['location_name_to_id']
                    id_to_name = {v: k for k, v in name_to_id.items()}
                    location_db[game_name] = id_to_name

        print("Mapping Player IDs...")
        player_db = {} 
        if 'slot_info' in data:
            for slot_id, slot_obj in data['slot_info'].items():
                p_name, p_game = resolve_player_info(slot_obj, slot_id)
                player_db[slot_id] = {'name': p_name, 'game': p_game}

        # 4. Generate Report
        spheres_data = data['spheres']
        base_name = os.path.splitext(file_path)[0]
        output_file = f"{base_name}_spheres_readable.txt"
        
        print(f"Translating {len(spheres_data)} spheres to text...")

        with open(output_file, "w", encoding="utf-8") as out:
            out.write(f"=== READABLE SPHERES REPORT ===\n")
            out.write(f"Source: {os.path.basename(file_path)}\n")
            out.write(f"Total Spheres: {len(spheres_data)}\n")
            out.write("="*60 + "\n\n")

            count_dict = {}
            for i, sphere in enumerate(spheres_data):
                out.write(f"--- Sphere {i + 1} ---\n")
                if not sphere:
                    out.write("  (Empty Sphere)\n")
                    continue
                if i != 0:
                    break  # Only process Sphere 1 for check counts
                for player_id in sorted(sphere.keys()):
                    location_ids = sphere[player_id]
                    p_info = player_db.get(player_id, {'name': f"Player {player_id}", 'game': 'Unknown'})
                    count_dict[player_id] = 0

                    out.write(f"  Player: {p_info['name']} ({p_info['game']})\n")
                    
                    loc_map = location_db.get(p_info['game'], {})
                    for loc_id in sorted(location_ids):
                        loc_name = loc_map.get(loc_id, f"Unknown ID {loc_id}")
                        out.write(f"    - {loc_name}\n")
                        count_dict[player_id] += 1
                    out.write("\n")
                out.write("\n")
                sorted_count = sorted(count_dict.items(), key=lambda x: x[1], reverse=True)
            out.write("=== SPHERE 1 CHECK COUNT RANKING ===\n")
            for player_id, count in sorted_count:
                p_info = player_db.get(player_id, {'name': f"Player {player_id}", 'game': 'Unknown'})
                out.write(f"  Player: {p_info['name']} ({p_info['game']}), Checks: {count}\n")

        print(f"SUCCESS: Report generated: {output_file}")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_archipelago_spheres.py <your_file.archipelago>")
        print("You can drag and drop the .archipelago file onto this script.")
        input("Press Enter to exit...")
    else:
        file_path = sys.argv[1]
        process_archipelago_file(file_path)
        input("\nPress Enter to close...")