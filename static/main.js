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

document.addEventListener("DOMContentLoaded", (event) => {
    const rows = document.getElementsByClassName("file-entry");
    for (let row of rows) {
        row.addEventListener("click", op_get);
    }

    const deletes = document.getElementsByClassName("delete-button");
    for (let button of deletes) {
        button.addEventListener("click", op_delete);
    }

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
