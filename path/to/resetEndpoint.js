const express = require('express');
const app = express();

app.use(express.json());

app.post('/reset', (req, res) => {
    // Check if task body is present
    const task = req.body.task;

    // If no task is provided, handle empty request
    if (!task) {
        return res.status(400).json({ message: 'Task body is required.' });
    }

    // Add your logic to handle the reset with the provided task
    res.status(200).json({ message: `Reset initiated with task: ${task}` });
});

module.exports = app;