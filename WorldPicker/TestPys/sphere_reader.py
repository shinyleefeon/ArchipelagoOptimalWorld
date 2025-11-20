import pickle
import pprint
import os
import sys
import pickletools
import io

# --- Placeholder Object ---
class PlaceholderObject:
    # CRITICAL CHANGE: Capture data passed to __new__ (Constructor)
    # This is required if pickle uses NEWOBJ with arguments.
    def __new__(cls, *args, **kwargs):
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

        # 1. Check _state
        state = self.__dict__.get("_state")
        if isinstance(state, dict) and name in state: return state[name]
        if isinstance(state, tuple) and len(state) == 2:
            if isinstance(state[0], dict) and name in state[0]: return state[0][name]
            if isinstance(state[1], dict) and name in state[1]: return state[1][name]

        # 2. Check _new_args (Data passed to constructor)
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
# -----------------------------------------------------------------------

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

def analyze_pickle_stream(file_path):
    """Uses pickletools to print the first few ops if extraction fails."""
    print("\n" + "!"*60)
    print("[DEBUG] Running pickletools analysis to diagnose data format...")
    try:
        with open(file_path, "rb") as f:
            content = f.read(500) 
            try:
                gen = pickletools.genops(content)
                print("--- Pickle Opcodes (First 500 bytes) ---")
                for op in gen:
                    print(f"{op[0].name} {op[1] if op[1] is not None else ''}")
                    if op[1] == 'NetworkSlot':
                        print("... (Found NetworkSlot, stopping trace) ...")
                        break
            except Exception as e:
                print(f"Analysis error: {e}")
    except Exception as e:
        print(f"Could not read file for analysis: {e}")
    print("!"*60 + "\n")

def extract_readable_spheres(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found at path: {file_path}")
        return None

    print(f"Loading: {file_path}")
    try:
        with open(file_path, 'rb') as f:
            data = SafeUnpickler(f).load()
        
        print("Data loaded successfully.")
        
        if 'spheres' not in data:
            print("Error: 'spheres' key not found.")
            return

        # --- 1. Build Location Database ---
        print("Building Location Database...")
        location_db = {} 
        if 'datapackage' in data:
            for game_name, game_data in data['datapackage'].items():
                if 'location_name_to_id' in game_data:
                    name_to_id = game_data['location_name_to_id']
                    id_to_name = {v: k for k, v in name_to_id.items()}
                    location_db[game_name] = id_to_name

        # --- 2. Build Player Database ---
        print("Building Player Database...")
        player_db = {} 
        extraction_failed = False
        
        if 'slot_info' in data:
            for slot_id, slot_obj in data['slot_info'].items():
                p_name, p_game = resolve_player_info(slot_obj, slot_id)

                if (p_name == "Unknown" or p_game == "Unknown") and not extraction_failed:
                    print(f"\n[FAILURE] Could not resolve info for Slot {slot_id}")
                    print(f"Object internals: {slot_obj.__dict__}")
                    extraction_failed = True

                player_db[slot_id] = {'name': p_name, 'game': p_game}

        if extraction_failed:
            analyze_pickle_stream(file_path)

        # --- 3. Generate Readable Report ---
        spheres_data = data['spheres']
        base_name = os.path.splitext(file_path)[0]
        output_file = f"output.txt"
        
        print(f"Translating {len(spheres_data)} spheres...")

        with open(output_file, "w", encoding="utf-8") as out:
            out.write(f"=== READABLE SPHERES REPORT ===\n")
            out.write(f"Source: {os.path.basename(file_path)}\n")
            out.write(f"Total Spheres: {len(spheres_data)}\n")
            out.write("="*60 + "\n\n")

            for i, sphere in enumerate(spheres_data):
                out.write(f"--- Sphere {i + 1} ---\n")
                if not sphere:
                    out.write("  (Empty Sphere)\n")
                    continue

                for player_id in sorted(sphere.keys()):
                    location_ids = sphere[player_id]
                    p_info = player_db.get(player_id, {'name': f"Player {player_id}", 'game': 'Unknown'})
                    out.write(f"  Player: {p_info['name']} ({p_info['game']})\n")
                    
                    loc_map = location_db.get(p_info['game'], {})
                    for loc_id in sorted(location_ids):
                        loc_name = loc_map.get(loc_id, f"Unknown ID {loc_id}")
                        out.write(f"    - {loc_name}\n")
                    out.write("\n")
                out.write("\n")

        print(f"SUCCESS: Readable report written to: {output_file}")

    except Exception as e:
        print(f"Error processing file: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python read_pickle.py <path_to_file.raw.pickle>")
        input("Press Enter to exit...")
    else:
        file_path = sys.argv[1]
        extract_readable_spheres(file_path)
        input("\nPress Enter to close...")