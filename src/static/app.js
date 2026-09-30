document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const aiStatusBadge = document.getElementById('aiStatusBadge');
  const aiBadgeDot = document.getElementById('aiBadgeDot');
  const aiStatusText = document.getElementById('aiStatusText');
  const referenceCountBadge = document.getElementById('referenceCountBadge');

  const fileDropzone = document.getElementById('fileDropzone');
  const fileInput = document.getElementById('fileInput');
  const browseBtn = document.getElementById('browseBtn');

  const runTankDemoBtn = document.getElementById('runTankDemoBtn');
  const runDryDemoBtn = document.getElementById('runDryDemoBtn');
  const customApiKeyInput = document.getElementById('customApiKeyInput');
  const saveApiKeyBtn = document.getElementById('saveApiKeyBtn');

  const processingBanner = document.getElementById('processingBanner');
  const processingTitle = document.getElementById('processingTitle');
  const processingSubtitle = document.getElementById('processingSubtitle');

  const resultsSection = document.getElementById('resultsSection');
  const metricContainers = document.getElementById('metricContainers');
  const metricSuccess = document.getElementById('metricSuccess');
  const metricReview = document.getElementById('metricReview');
  const metricConfidence = document.getElementById('metricConfidence');

  const downloadSuccessBtn = document.getElementById('downloadSuccessBtn');
  const downloadFailedBtn = document.getElementById('downloadFailedBtn');
  const invoicesContainer = document.getElementById('invoicesContainer');

  // Review Modal Elements
  const reviewModal = document.getElementById('reviewModal');
  const closeModalBtn = document.getElementById('closeModalBtn');
  const cancelReviewBtn = document.getElementById('cancelReviewBtn');
  const reviewForm = document.getElementById('reviewForm');
  const modalJobId = document.getElementById('modalJobId');
  const modalContainerId = document.getElementById('modalContainerId');
  const modalRoute = document.getElementById('modalRoute');
  const modalDescription = document.getElementById('modalDescription');
  const modalCodeInput = document.getElementById('modalCodeInput');
  const modalFeedback = document.getElementById('modalFeedback');

  let currentInvoices = [];
  let currentActiveReviewJob = null;
  let currentActiveInvoice = null;

  // Custom API key session state
  let sessionApiKey = sessionStorage.getItem('eor_gemini_api_key') || '';
  if (sessionApiKey && customApiKeyInput) {
    customApiKeyInput.value = sessionApiKey;
  }

  // 1. Initial Health Check
  async function checkHealth() {
    try {
      const res = await fetch('/api/health');
      if (!res.ok) throw new Error('Health check failed');
      const data = await res.json();

      if (data.gemini_configured || sessionApiKey) {
        aiBadgeDot.className = 'badge-dot active';
        aiStatusText.textContent = 'Gemini AI: Active';
      } else {
        aiBadgeDot.className = 'badge-dot';
        aiStatusText.textContent = 'Gemini: Demo Key Needed';
      }
    } catch (err) {
      aiBadgeDot.className = 'badge-dot error';
      aiStatusText.textContent = 'Server Offline';
    }
  }

  // 2. Fetch Reference Counts
  async function fetchReferenceCounts() {
    try {
      const res = await fetch('/api/reference-mappings');
      if (res.ok) {
        const data = await res.json();
        const totalCodes = (data.tank_codes_count || 0) + (data.dry_codes_count || 0) + (data.iso_codes_count || 0);
        referenceCountBadge.textContent = `${totalCodes.toLocaleString()}+ Standard Codes`;
      }
    } catch (err) {
      console.warn('Could not fetch reference counts', err);
    }
  }

  checkHealth();
  fetchReferenceCounts();

  // Save session API key
  if (saveApiKeyBtn) {
    saveApiKeyBtn.addEventListener('click', () => {
      const key = customApiKeyInput.value.trim();
      sessionApiKey = key;
      if (key) {
        sessionStorage.setItem('eor_gemini_api_key', key);
        aiBadgeDot.className = 'badge-dot active';
        aiStatusText.textContent = 'Gemini AI: Key Set';
        alert('Custom Gemini API key saved for this browser session.');
      } else {
        sessionStorage.removeItem('eor_gemini_api_key');
        checkHealth();
      }
    });
  }

  // 3. Dropzone & File Selection Handlers
  browseBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput.click();
  });

  fileDropzone.addEventListener('click', () => {
    fileInput.click();
  });

  fileDropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    fileDropzone.classList.add('dragover');
  });

  fileDropzone.addEventListener('dragleave', () => {
    fileDropzone.classList.remove('dragover');
  });

  fileDropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    fileDropzone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      uploadFile(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files && fileInput.files.length > 0) {
      uploadFile(fileInput.files[0]);
    }
  });

  // 4. File Upload Request
  async function uploadFile(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['pdf', 'xlsx', 'xls'].includes(ext)) {
      alert('Please upload a PDF (.pdf) or Excel (.xlsx, .xls) document.');
      return;
    }

    setProcessing(true, 'Extracting Document Content...', `Ingesting ${file.name} with layout preservation.`);

    const formData = new FormData();
    formData.append('file', file);

    const headers = {};
    if (sessionApiKey) {
      headers['X-Gemini-Key'] = sessionApiKey;
    }

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        headers: headers,
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: 'Upload error' }));
        throw new Error(errData.detail || 'Processing failed');
      }

      const result = await res.json();
      renderResults(result);
    } catch (err) {
      alert(`Error processing file: ${err.message}`);
    } finally {
      setProcessing(false);
      fileInput.value = '';
    }
  }

  // 5. 1-Click Demo Handlers
  runTankDemoBtn.addEventListener('click', () => runDemo('tank'));
  runDryDemoBtn.addEventListener('click', () => runDemo('dry'));

  async function runDemo(sampleType) {
    const title = sampleType === 'tank' ? 'Tank Container (22K1)' : 'Dry Cargo Box (42G1)';
    setProcessing(true, `Processing Demo: ${title}`, 'Standardizing lines against CEDEX master references...');

    const headers = { 'Content-Type': 'application/json' };
    if (sessionApiKey) {
      headers['X-Gemini-Key'] = sessionApiKey;
    }

    try {
      const res = await fetch('/api/process-demo', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ sample_type: sampleType }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Demo processing failed' }));
        throw new Error(err.detail || 'Demo processing failed');
      }

      const result = await res.json();
      renderResults(result);
    } catch (err) {
      alert(`Demo Execution Error: ${err.message}`);
    } finally {
      setProcessing(false);
    }
  }

  function setProcessing(active, title = '', subtitle = '') {
    if (active) {
      processingBanner.classList.remove('hidden');
      processingTitle.textContent = title;
      processingSubtitle.textContent = subtitle;
      resultsSection.classList.add('hidden');
    } else {
      processingBanner.classList.add('hidden');
    }
  }

  // 6. Render Results & Metrics
  function renderResults(result) {
    resultsSection.classList.remove('hidden');
    currentInvoices = result.invoices || [];

    metricContainers.textContent = result.total_estimates || currentInvoices.length;
    metricSuccess.textContent = result.success_count || 0;
    metricReview.textContent = result.review_count || 0;

    // Overall Confidence
    if (currentInvoices.length > 0) {
      const avgScore = (
        currentInvoices.reduce((acc, inv) => acc + (inv.confidence_score || 0.8), 0) / currentInvoices.length
      ).toFixed(2);
      metricConfidence.textContent = `${Math.round(avgScore * 100)}%`;
    } else {
      metricConfidence.textContent = '100%';
    }

    // Configure Download Buttons
    if (result.success_report_file) {
      downloadSuccessBtn.disabled = false;
      downloadSuccessBtn.onclick = () => {
        window.open(`/api/download-report/${result.success_report_file}`, '_blank');
      };
    } else {
      downloadSuccessBtn.disabled = true;
    }

    if (result.failed_report_file) {
      downloadFailedBtn.disabled = false;
      downloadFailedBtn.onclick = () => {
        window.open(`/api/download-report/${result.failed_report_file}`, '_blank');
      };
    } else {
      downloadFailedBtn.disabled = true;
    }

    // Render Invoices Table
    renderInvoicesList(currentInvoices);

    // Smooth scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function renderInvoicesList(invoices) {
    invoicesContainer.innerHTML = '';

    if (!invoices || invoices.length === 0) {
      invoicesContainer.innerHTML = `<div class="card" style="text-align: center; color: var(--text-muted);">No repair estimates found.</div>`;
      return;
    }

    invoices.forEach((inv, invIndex) => {
      const card = document.createElement('div');
      card.className = 'invoice-card';

      const routePillClass = inv.route === 'tank' ? 'pill-tank' : 'pill-dry';
      const hasReview = inv.review_needed_count > 0;
      const statusPillClass = hasReview ? 'pill-warning' : 'pill-success';
      const statusText = hasReview ? `${inv.review_needed_count} Needs Review` : 'Verified Mapped';

      card.innerHTML = `
        <div class="invoice-header">
          <div class="invoice-title-group">
            <span class="container-badge">${inv.container_id || 'UNKNOWN'}</span>
            <span class="pill ${routePillClass}">${inv.route || 'tank'} route</span>
            <span class="pill ${statusPillClass}">${statusText}</span>
          </div>
          <div class="invoice-meta">
            <div><strong>ISO Type:</strong> ${inv.container_type || '22K1'}</div>
            <div><strong>Depot:</strong> ${inv.depot_name || 'Terminal'}</div>
            <div><strong>Confidence:</strong> ${Math.round((inv.confidence_score || 0.8) * 100)}%</div>
          </div>
        </div>

        <div class="table-responsive">
          <table class="jobs-table">
            <thead>
              <tr>
                <th>Job #</th>
                <th>Description</th>
                <th>LOCN</th>
                <th>CMP</th>
                <th>RPR</th>
                <th>DMG</th>
                <th>CEDEX Code</th>
                <th>Hours / Cost</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody id="jobsTbody-${invIndex}">
            </tbody>
          </table>
        </div>
      `;

      invoicesContainer.appendChild(card);
      const tbody = document.getElementById(`jobsTbody-${invIndex}`);

      (inv.jobs || []).forEach((job) => {
        const tr = document.createElement('tr');
        const isMapped = job.status === 'mapped' || job.status === 'reviewed';
        const statusBadge = isMapped
          ? `<span class="pill pill-success">Mapped</span>`
          : `<span class="pill pill-warning">Review Needed</span>`;

        const cedexDisplay = job.cedex_code
          ? `<span class="cedex-full-code">${job.cedex_code}</span>`
          : `<span style="color: var(--text-muted); font-size: 0.8rem;">--</span>`;

        const actionBtn = isMapped
          ? `<span class="btn-verified">Mapped</span>`
          : `<button class="btn-review review-trigger-btn">Review &amp; Map</button>`;

        const manhours = job.manhour || 0;
        const totalCost = (job.labour_cost || 0) + (job.material_cost_aed || 0);

        tr.innerHTML = `
          <td><strong>#${job.job_id || 1}</strong></td>
          <td class="job-desc-cell">
            <div class="raw-desc">${escapeHtml(job.job_description || '')}</div>
            ${job.display_description && job.display_description !== job.job_description ? `<div class="translated-desc">🔤 ${escapeHtml(job.display_description)}</div>` : ''}
          </td>
          <td><span class="code-pill">${job.location || '--'}</span></td>
          <td><span class="code-pill">${job.component || '--'}</span></td>
          <td><span class="code-pill">${job.repair || '--'}</span></td>
          <td><span class="code-pill">${job.damage || '--'}</span></td>
          <td>${cedexDisplay}</td>
          <td>${manhours}h &bull; $${totalCost.toFixed(2)}</td>
          <td>${statusBadge}</td>
          <td>${actionBtn}</td>
        `;

        if (!isMapped) {
          const btn = tr.querySelector('.review-trigger-btn');
          btn.addEventListener('click', () => {
            openReviewModal(job, inv);
          });
        }

        tbody.appendChild(tr);
      });
    });
  }

  // 7. Human Review Modal Logic
  function openReviewModal(job, invoice) {
    currentActiveReviewJob = job;
    currentActiveInvoice = invoice;

    modalJobId.textContent = `#${job.job_id}`;
    modalContainerId.textContent = invoice.container_id;
    modalRoute.textContent = invoice.route;
    modalDescription.textContent = job.display_description || job.job_description || '';

    // Suggest default prefix if partial codes exist
    const loc = (job.location || 'BX').substring(0, 2);
    const cmp = job.component || '';
    const rpr = job.repair || '';
    const dmg = job.damage || '';
    modalCodeInput.value = `${loc}XX ${cmp} ${rpr} ${dmg}`.trim();

    modalFeedback.className = 'modal-feedback hidden';
    reviewModal.classList.remove('hidden');
    modalCodeInput.focus();
  }

  function closeReviewModal() {
    reviewModal.classList.add('hidden');
    currentActiveReviewJob = null;
    currentActiveInvoice = null;
  }

  closeModalBtn.addEventListener('click', closeReviewModal);
  cancelReviewBtn.addEventListener('click', closeReviewModal);

  reviewForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!currentActiveReviewJob || !currentActiveInvoice) return;

    const codeInput = modalCodeInput.value.trim();
    if (!codeInput) return;

    modalFeedback.className = 'modal-feedback hidden';

    try {
      const res = await fetch('/api/review-job', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_id: currentActiveReviewJob.job_id,
          route: currentActiveInvoice.route,
          human_code_input: codeInput,
          raw_job: currentActiveReviewJob,
        }),
      });

      const data = await res.json();

      if (!res.ok || !data.success) {
        modalFeedback.className = 'modal-feedback error';
        modalFeedback.textContent = data.message || 'Verification failed against CEDEX Master reference.';
        modalFeedback.classList.remove('hidden');
        return;
      }

      // Success
      modalFeedback.className = 'modal-feedback success';
      modalFeedback.textContent = data.message || 'Mapping saved!';
      modalFeedback.classList.remove('hidden');

      // Update local object
      if (data.updated_job) {
        Object.assign(currentActiveReviewJob, data.updated_job);
        currentActiveReviewJob.status = 'reviewed';
        currentActiveReviewJob.needs_human_review = false;
        if (currentActiveInvoice.review_needed_count > 0) {
          currentActiveInvoice.review_needed_count -= 1;
        }
      }

      setTimeout(() => {
        closeReviewModal();
        renderInvoicesList(currentInvoices);
        fetchReferenceCounts();
      }, 700);
    } catch (err) {
      modalFeedback.className = 'modal-feedback error';
      modalFeedback.textContent = `Server error: ${err.message}`;
      modalFeedback.classList.remove('hidden');
    }
  });

  function escapeHtml(text) {
    if (!text) return '';
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
});
