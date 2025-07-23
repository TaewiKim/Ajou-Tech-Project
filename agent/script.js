document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('canvas');
    const switchPatternBtn = document.getElementById('switch-pattern');
    const clearCanvasBtn = document.getElementById('clear-canvas');

    // Patterns with characters and corresponding musical scales (C Major and G Major pentatonic)
    const patterns = [
        {
            name: 'Cosmic',
            characters: ['*', '+', 'o', '.', '#'],
            scale: [261.63, 293.66, 329.63, 349.23, 392.00] // C Major Pentatonic
        },
        {
            name: 'Money',
            characters: ['@', '$', '&', '%', '!'],
            scale: [392.00, 440.00, 493.88, 523.25, 587.33] // G Major Pentatonic
        },
        {
            name: 'Lines',
            characters: ['/', '\\', '-', '_', '|'],
            scale: [523.25, 587.33, 659.25, 698.46, 783.99] // C Major Scale (higher octave)
        }
    ];

    let currentPattern = 0;
    let isDrawing = false;
    let audioContext;

    // Initialize AudioContext on user interaction
    function initAudio() {
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
    }

    // Create the grid of cells for the canvas
    function createGrid() {
        canvas.innerHTML = ''; // Clear previous grid
        // Adjust grid size based on container
        const canvasWidth = canvas.clientWidth;
        const canvasHeight = canvas.clientHeight;
        const cellSize = 15;
        const numCols = Math.floor(canvasWidth / cellSize);
        const numRows = Math.floor(canvasHeight / cellSize);
        
        canvas.style.gridTemplateColumns = `repeat(${numCols}, ${cellSize}px)`;

        for (let i = 0; i < numCols * numRows; i++) {
            const cell = document.createElement('div');
            cell.classList.add('cell');
            canvas.appendChild(cell);
        }
    }

    // Draw a character in a cell and play a sound
    function draw(targetCell) {
        if (!targetCell || !targetCell.classList.contains('cell')) return;

        const pattern = patterns[currentPattern];
        const charIndex = Math.floor(Math.random() * pattern.characters.length);
        const character = pattern.characters[charIndex];
        const frequency = pattern.scale[charIndex];

        targetCell.textContent = character;
        playSound(frequency);
    }

    // Play a musical note
    function playSound(frequency) {
        if (!audioContext) return;

        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();

        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(frequency, audioContext.currentTime);
        
        gainNode.gain.setValueAtTime(0.5, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.5);

        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);

        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.5);
    }

    // Event Listeners
    function setupEventListeners() {
        // Use event delegation on the canvas
        canvas.addEventListener('mousedown', (e) => {
            initAudio(); // Initialize audio on first click
            isDrawing = true;
            draw(e.target);
        });

        canvas.addEventListener('mouseover', (e) => {
            if (isDrawing) {
                draw(e.target);
            }
        });

        // Stop drawing when mouse leaves canvas or button is released
        document.addEventListener('mouseup', () => {
            isDrawing = false;
        });
        canvas.addEventListener('mouseleave', () => {
            isDrawing = false;
        });

        // Touch events
        canvas.addEventListener('touchstart', (e) => {
            e.preventDefault();
            initAudio();
            isDrawing = true;
            const touch = e.touches[0];
            const targetCell = document.elementFromPoint(touch.clientX, touch.clientY);
            draw(targetCell);
        }, { passive: false });

        canvas.addEventListener('touchmove', (e) => {
            e.preventDefault();
            if (isDrawing) {
                const touch = e.touches[0];
                const targetCell = document.elementFromPoint(touch.clientX, touch.clientY);
                draw(targetCell);
            }
        }, { passive: false });

        canvas.addEventListener('touchend', () => {
            isDrawing = false;
        });

        // Control buttons
        switchPatternBtn.addEventListener('click', () => {
            currentPattern = (currentPattern + 1) % patterns.length;
            // Optional: display current pattern name
            console.log(`Switched to pattern: ${patterns[currentPattern].name}`);
        });

        clearCanvasBtn.addEventListener('click', () => {
            const cells = canvas.querySelectorAll('.cell');
            cells.forEach(cell => {
                cell.textContent = '';
            });
        });
        
        // Recreate grid on window resize
        window.addEventListener('resize', createGrid);
    }

    // Initial setup
    createGrid();
    setupEventListeners();
});