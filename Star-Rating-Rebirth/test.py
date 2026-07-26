import os
import algorithm

folder_path = 'Test'  # Update this to the path of your Test folder

# Traverse the directory and process each .osu file
for root, dirs, files in os.walk(folder_path):
    for file in files:
        if file.endswith('.osu'):
            file_path = os.path.join(root, file)
            result = algorithm.calculate(file_path, 'NM')
            print(file, "|", f'{result:.4f}')
