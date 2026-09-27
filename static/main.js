let rename_target;

function op_get(event) {
    window.location.href = event.currentTarget.dataset.href;
}

function op_delete(event) {
    event.stopPropagation();
    const location = event.target.parentElement.parentElement.parentElement.dataset.href;
    fetch(location, { method: "DELETE" }).then(
        () => {
            window.location.reload();
        }
    );
}

function op_rename(event) {
    if (event.currentTarget.returnValue !== "save") {
        return;
    }
    const new_name_input = document.getElementById("rename-form-name");
    fetch(rename_target, {
        method: "PATCH",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            new_path: CURRENT_PATH + "/" + new_name_input.value
        })
    }).then(
        () => {
            window.location.reload();
        }
    );
}

function open_rename_dialog(event) {
    event.stopPropagation();
    const location = event.target.parentElement.parentElement.parentElement.dataset.href;
    rename_target = location;
}

document.addEventListener("DOMContentLoaded", (event) => {
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

    const upload_input = document.getElementById("upload-input");
    const upload_name = document.getElementById("upload-name");
    const upload_form = document.getElementById("upload-form");
    if (upload_input !== null) {
        upload_input.addEventListener("change", (event) => {
            const file = event.target.files[0];
            upload_name.innerText = "Submit '" + file.name + "'";
            upload_name.style.display = "inline";
        });
        upload_name.addEventListener("click", (event) => {
            upload_form.submit();
        });
    }

    console.log("Set event listeners!");
});
