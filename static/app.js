// Theme Toggle
function toggleTheme() {
    const body = document.body;
    const toggleBtn = document.querySelector('.theme-toggle');
    
    body.classList.toggle('dark');
    
    const isDark = body.classList.contains('dark');
    toggleBtn.textContent = isDark ? '☀️' : '🌙';
    
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
}

// Load saved theme preference
function loadTheme() {
    const savedTheme = localStorage.getItem('theme');
    const toggleBtn = document.querySelector('.theme-toggle');
    
    if (savedTheme === 'dark') {
        document.body.classList.add('dark');
        if (toggleBtn) toggleBtn.textContent = '☀️';
    } else if (savedTheme === 'light') {
        document.body.classList.remove('dark');
        if (toggleBtn) toggleBtn.textContent = '🌙';
    }
    // If no saved preference, rely on CSS media query
}

loadTheme();

document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('file-input');
    const dropzone = document.getElementById('dropzone');
    const uploadForm = document.getElementById('upload-form');
    
    if (dropzone && fileInput) {
        dropzone.addEventListener('click', () => fileInput.click());
        
        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.style.borderColor = '#6366f1';
        });
        
        dropzone.addEventListener('dragleave', () => {
            dropzone.style.borderColor = '#e5e7eb';
        });
        
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.style.borderColor = '#e5e7eb';
            if (e.dataTransfer.files.length) {
                fileInput.files = e.dataTransfer.files;
                handleFileSelect();
            }
        });
        
        fileInput.addEventListener('change', handleFileSelect);
    }
    
    function handleFileSelect() {
        if (fileInput.files.length > 0) {
            const files = Array.from(fileInput.files);
            const progressDiv = document.getElementById('upload-progress');
            const countSpan = document.getElementById('upload-count');
            const totalSpan = document.getElementById('upload-total');
            const progressBar = document.getElementById('progress-bar');
            
            progressDiv.style.display = 'block';
            totalSpan.textContent = files.length;
            countSpan.textContent = '0';
            progressBar.style.width = '0%';
            
            let uploaded = 0;
            
            function uploadNext(index) {
                if (index >= files.length) {
                    window.location.href = '/gallery?success=uploaded';
                    return;
                }
                
                const formData = new FormData();
                formData.append('files', files[index]);
                
                fetch('/upload', {
                    method: 'POST',
                    body: formData
                }).then(() => {
                    uploaded++;
                    countSpan.textContent = uploaded;
                    progressBar.style.width = (uploaded / files.length * 100) + '%';
                    uploadNext(index + 1);
                }).catch(() => {
                    uploadNext(index + 1);
                });
            }
            
            uploadNext(0);
        }
    }
    
    const selectAll = document.getElementById('select-all');
    const photoCheckboxes = document.querySelectorAll('.photo-checkbox');
    const downloadBtn = document.getElementById('download-selected');
    
    if (selectAll) {
        selectAll.addEventListener('change', () => {
            photoCheckboxes.forEach(cb => {
                cb.checked = selectAll.checked;
            });
            updateSelectedCount();
        });
    }
    
    photoCheckboxes.forEach(cb => {
        cb.addEventListener('change', updateSelectedCount);
    });
    
    function updateSelectedCount() {
        const selected = document.querySelectorAll('.photo-checkbox:checked').length;
        const countEl = document.getElementById('selected-count');
        if (countEl) {
            countEl.textContent = selected;
        }
        if (downloadBtn) {
            downloadBtn.disabled = selected === 0;
        }
    }
    
    if (downloadBtn) {
        downloadBtn.addEventListener('click', () => {
            const selected = Array.from(document.querySelectorAll('.photo-checkbox:checked'))
                .map(cb => cb.value);
            
            if (selected.length === 0) return;
            
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = '/download';
            
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'photo_ids';
            input.value = selected.join(',');
            
            form.appendChild(input);
            document.body.appendChild(form);
            form.submit();
            document.body.removeChild(form);
        });
    }
    
    const modal = document.getElementById('photo-modal');
    const modalImg = document.getElementById('modal-img');
    const modalClose = document.getElementById('modal-close');
    
    document.querySelectorAll('.photo-card img').forEach(img => {
        img.addEventListener('click', () => {
            const photoId = img.closest('.photo-card').querySelector('.photo-checkbox')?.value;
            if (photoId) {
                modalImg.src = `/api/photos/${photoId}/full`;
                modal.classList.add('active');
            }
        });
    });
    
    if (modalClose) {
        modalClose.addEventListener('click', () => {
            modal.classList.remove('active');
        });
    }
    
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
            }
        });
    }
});
