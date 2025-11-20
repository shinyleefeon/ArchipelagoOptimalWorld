import pickle
import pprint
import os
import sys

# --- Copying the SafeUnpickler class so this script works standalone ---
class PlaceholderObject:
    def __init__(self, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs
        self._state = None
    def __repr__(self):
        # Return a clean representation of the class
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
                # Create a dynamic class that inherits from PlaceholderObject
                new_class = type(name, (PlaceholderObject,), {
                    "__module__": module
                })
                self.known_placeholders[key] = new_class
            return self.known_placeholders[key]
# -----------------------------------------------------------------------

def load_my_pickle(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found at path: {file_path}")
        return None

    print(f"Loading: {file_path}")
    try:
        with open(file_path, 'rb') as f:
            # Use SafeUnpickler instead of pickle.load(f)
            data = SafeUnpickler(f).load()
        
        print("Data loaded successfully!")
        print("-" * 40)
        print("Here are the top-level keys in the data:")
        if isinstance(data, dict):
            print(list(data.keys()))
        else:
            print(f"Data is not a dict, it is type: {type(data)}")
            print(data)
        print("-" * 40)

        return data

    except Exception as e:
        print(f"Error loading pickle: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python read_pickle.py <path_to_file.raw.pickle>")
        print("You can drag and drop the file onto this script.")
        input("Press Enter to exit...")
    else:
        file_path = sys.argv[1]
        # Load the data
        my_data = load_my_pickle(file_path)
        
        # Keep window open if double-clicked
        input("\nPress Enter to close...")