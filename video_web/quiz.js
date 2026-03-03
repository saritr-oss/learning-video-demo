/* ============================================================
   Quiz Engine — quiz.js
   Demo mode: auto-selects random answers, then submits
   ============================================================ */
(function () {
    'use strict';

    // ── Helpers ──
    const $ = id => document.getElementById(id);

    // ── State ──
    let quizData = null;
    let userAnswers = {};
    let currentAutoIdx = 0;

    // ── Load quiz data from persona folder, skip if not found ──
    const _persona = new URLSearchParams(window.location.search).get('persona') || '';
    if (!_persona) {
        window.location.href = 'select.html';
    } else {
        fetch('persona/' + _persona + '/quiz.json')
            .then(function (r) {
                if (!r.ok) throw new Error('no quiz');
                return r.json();
            })
            .then(function (data) {
                quizData = data;
                init();
            })
            .catch(function () {
                // No quiz for this persona — return to course selection
                window.location.href = 'select.html';
            });
    }

    function init() {
        $('quiz-title').textContent = quizData.title;

        // Build all questions on the page
        const container = $('options-list');
        container.innerHTML = '';

        quizData.questions.forEach((q, idx) => {
            const qBlock = document.createElement('div');
            qBlock.className = 'quiz-question-block';
            qBlock.id = 'q-block-' + q.id;

            // Question label
            const label = document.createElement('div');
            label.className = 'q-label';
            label.textContent = q.label;
            qBlock.appendChild(label);

            // Scenario
            const scenario = document.createElement('div');
            scenario.className = 'q-scenario';
            scenario.textContent = q.scenario;
            qBlock.appendChild(scenario);

            // Options
            const optionsWrap = document.createElement('div');
            optionsWrap.className = 'q-options';

            q.options.forEach(opt => {
                const optBtn = document.createElement('div');
                optBtn.className = 'q-option';
                optBtn.id = 'opt-' + q.id + '-' + opt.label;
                optBtn.innerHTML = '<span class="opt-label">' + opt.label + '</span><span class="opt-text">' + opt.text + '</span>';
                optionsWrap.appendChild(optBtn);
            });

            qBlock.appendChild(optionsWrap);
            container.appendChild(qBlock);
        });

        // Build progress dots
        const dotsEl = $('progress-dots');
        dotsEl.innerHTML = '';
        quizData.questions.forEach((q, i) => {
            const dot = document.createElement('span');
            dot.className = 'prog-dot';
            dot.id = 'dot-' + q.id;
            dotsEl.appendChild(dot);
        });

        // Show question card
        $('question-card').classList.remove('hidden');
        $('quiz-progress').textContent = 'Reading questions...';

        // Show all questions for 5 seconds, then start auto-answering
        setTimeout(startAutoAnswer, 5000);
    }

    // ── Random answer picker ──
    // Picks a random option label (A/B/C/D), biased 60% toward correct
    function pickRandomAnswer(q) {
        const labels = q.options.map(o => o.label);
        if (Math.random() < 0.6) {
            return q.correct; // 60% chance correct
        }
        // Pick a random wrong answer
        const wrong = labels.filter(l => l !== q.correct);
        return wrong[Math.floor(Math.random() * wrong.length)];
    }

    // ── Auto-answer sequence ──
    function startAutoAnswer() {
        currentAutoIdx = 0;
        $('quiz-progress').textContent = 'Answering...';
        autoAnswerNext();
    }

    function autoAnswerNext() {
        if (currentAutoIdx >= quizData.questions.length) {
            // All answered — show submit button
            showSubmitButton();
            return;
        }

        const q = quizData.questions[currentAutoIdx];
        const selectedLabel = pickRandomAnswer(q);

        // Scroll to this question block
        const qBlock = $('q-block-' + q.id);
        if (qBlock) {
            qBlock.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }

        // Highlight the selected option after a short delay (simulate "thinking")
        setTimeout(function () {
            const optEl = $('opt-' + q.id + '-' + selectedLabel);
            if (optEl) {
                optEl.classList.add('selected');
            }

            // Update dot to show answered
            const dot = $('dot-' + q.id);
            if (dot) {
                dot.classList.add('dot-answered');
            }

            userAnswers[q.id] = selectedLabel;
            currentAutoIdx++;

            // Move to next after a pause
            setTimeout(autoAnswerNext, 2000);
        }, 800);
    }

    // ── Submit button ──
    function showSubmitButton() {
        $('quiz-progress').textContent = 'All answered — submitting...';

        const submitBtn = $('btn-submit');
        submitBtn.classList.remove('hidden');

        // Scroll to submit button
        submitBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });

        // Simulate clicking submit after 2 seconds
        setTimeout(function () {
            submitBtn.classList.add('pressing');
            setTimeout(function () {
                submitBtn.classList.remove('pressing');
                gradeAndShowResults();
            }, 400);
        }, 2000);
    }

    // ── Grade answers and reveal correct/incorrect ──
    function gradeAndShowResults() {
        // Show correct/incorrect on each question
        quizData.questions.forEach(q => {
            const chosen = userAnswers[q.id];
            const isCorrect = chosen === q.correct;
            const optEl = $('opt-' + q.id + '-' + chosen);

            if (isCorrect) {
                if (optEl) optEl.classList.add('correct');
            } else {
                if (optEl) optEl.classList.add('incorrect');
                // Show the correct answer
                const correctEl = $('opt-' + q.id + '-' + q.correct);
                if (correctEl) correctEl.classList.add('correct');
            }

            // Update dot
            const dot = $('dot-' + q.id);
            if (dot) {
                dot.classList.remove('dot-answered');
                dot.classList.add(isCorrect ? 'dot-correct' : 'dot-incorrect');
            }
        });

        // Scroll to top briefly, then show results
        window.scrollTo({ top: 0, behavior: 'smooth' });
        setTimeout(showResults, 1500);
    }

    // ── Results ──
    function showResults() {
        $('question-card').classList.add('hidden');
        $('btn-submit').classList.add('hidden');
        $('results-card').classList.remove('hidden');
        $('quiz-progress').textContent = 'Results';

        const maxScore = quizData.questions.length * quizData.pointsPerQuestion;
        $('score-max').textContent = '/' + maxScore;

        let totalScore = 0;
        const breakdownEl = $('breakdown-list');
        breakdownEl.innerHTML = '';

        quizData.questions.forEach(q => {
            const chosen = userAnswers[q.id];
            const isCorrect = chosen === q.correct;
            const points = isCorrect ? quizData.pointsPerQuestion : 0;
            totalScore += points;

            const row = document.createElement('div');
            row.className = 'breakdown-row ' + (isCorrect ? 'row-correct' : 'row-incorrect');

            const icon = document.createElement('span');
            icon.className = 'breakdown-icon';
            icon.textContent = isCorrect ? '✅' : '❌';

            const info = document.createElement('div');
            info.className = 'breakdown-info';

            const qTitle = document.createElement('div');
            qTitle.className = 'breakdown-title';
            qTitle.textContent = q.label;

            const qDetail = document.createElement('div');
            qDetail.className = 'breakdown-detail';
            if (isCorrect) {
                qDetail.textContent = 'Correct — ' + points + ' points';
            } else {
                qDetail.textContent = 'Selected: ' + chosen + ' — Correct: ' + q.correct + ' — 0 points';
            }

            info.appendChild(qTitle);
            info.appendChild(qDetail);

            if (!isCorrect && q.slideRef) {
                const reviewLink = document.createElement('a');
                reviewLink.className = 'breakdown-review-link';
                reviewLink.href = 'index.html?persona=' + encodeURIComponent(_persona) + '&slide=' + q.slideRef;
                reviewLink.textContent = '▶ Review this section';
                info.appendChild(reviewLink);
            }

            row.appendChild(icon);
            row.appendChild(info);

            const pts = document.createElement('span');
            pts.className = 'breakdown-pts';
            pts.textContent = points + '/' + quizData.pointsPerQuestion;
            row.appendChild(pts);

            breakdownEl.appendChild(row);
        });

        // Animate score
        animateScore(totalScore);

        // Set level
        const level = quizData.levels.find(l => totalScore >= l.min && totalScore <= l.max);
        if (level) {
            const levelEl = $('score-level');
            levelEl.textContent = level.emoji + ' ' + level.label;
            levelEl.style.color = level.color;
        }
    }

    function animateScore(target) {
        const el = $('score-value');
        let current = 0;
        const step = Math.max(1, Math.floor(target / 10));
        const interval = setInterval(function () {
            current += step;
            if (current >= target) {
                current = target;
                clearInterval(interval);
            }
            el.textContent = current;
        }, 80);
    }

})();
