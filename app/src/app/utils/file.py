from pathlib import Path


def file_list(num_of_files: int, directory):
    path = Path(directory)
    print("dir", path.name)
    # print("path", path)
    file_list = []
    cnt = 0
    for filepath in directory.iterdir():
        file_list.append(str(directory) + "/" + filepath.name)
        cnt += 1

        if cnt >= num_of_files:
            break

    return file_list
