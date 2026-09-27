let rename_target;
let error_dialog_node;
let error_text_node;

function show_error(message) {
    error_text_node.innerText = message;
    error_dialog_node.show();
}

function op_get(event) {
    window.location.href = event.currentTarget.dataset.href;
}

function op_delete(event) {
    event.stopPropagation();
    const location = event.target.parentElement.parentElement.parentElement.dataset.href;
    fetch(location, { method: "DELETE" }).then(
        (response) => {
            if (!response.ok) {
                response.json().then((result) => {
                    show_error(result.detail);
                })
                return;
            }
            window.location.reload();
        }
    );
}

function op_rename(event) {
    if (event.currentTarget.returnValue !== "save") {
        return;
    }
    const new_name_input = document.getElementById("rename-form-name");
    let new_path;
    if (new_name_input.value.startsWith("/")) {
        new_path = new_name_input.value;
    } else {
        new_path = CURRENT_PATH + "/" + new_name_input.value;
    }
    fetch(rename_target, {
        method: "PATCH",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            new_path: new_path
        })
    }).then(
        (response) => {
            if (!response.ok) {
                response.json().then((result) => {
                    show_error(result.detail);
                })
                return;
            }
            window.location.reload();
        }
    );
}

function op_mkdir(event) {
    if (event.currentTarget.returnValue !== "save") {
        return;
    }
    const name_input = document.getElementById("mkdir-form-name");
    let name = name_input.value;
    fetch(CURRENT_PATH, {
        method: "PUT",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            name: name
        })
    }).then(
        (response) => {
            if (!response.ok) {
                response.json().then((result) => {
                    show_error(result.detail);
                })
                return;
            }
            window.location.reload();
        }
    );
}

function open_rename_dialog(event) {
    event.stopPropagation();
    const location = event.target.parentElement.parentElement.parentElement.dataset.href;
    rename_target = location;
}
function stop_the_prop(event) {
    event.stopPropagation();
}

document.addEventListener("DOMContentLoaded", (event) => {
    error_dialog_node = document.getElementById("error-dialog");
    error_text_node = document.getElementById("error-content");

    const rows = document.getElementsByClassName("file-entry");
    for (let row of rows) {
        row.addEventListener("click", op_get);
    }

    const deletes = document.getElementsByClassName("delete-button");
    for (let button of deletes) {
        button.addEventListener("click", op_delete);
    }
    const renames = document.getElementsByClassName("rename-button");
    for (let button of renames) {
        // We handle the operation in a modal
        button.addEventListener("click", open_rename_dialog);
    }

    const rename_dialog = document.getElementById("rename-form-dialog");
    rename_dialog.addEventListener("close", op_rename);

    const mkdir_dialog = document.getElementById("mkdir-form-dialog");
    mkdir_dialog.addEventListener("close", op_mkdir);
    const mkdir_button = document.getElementById("mkdir-button");
    mkdir_button.addEventListener("click", stop_the_prop);

    const upload_input = document.getElementById("upload-input");
    const upload_name = document.getElementById("upload-name");
    const upload_form = document.getElementById("upload-form");
    if (upload_input !== null) {
        upload_input.addEventListener("change", (event) => {
            const file = event.target.files[0];
            upload_name.innerText = "Submit '" + file.name + "'";
            upload_name.style.display = "inline";
        });
    }

    console.log("Set event listeners!");
});
