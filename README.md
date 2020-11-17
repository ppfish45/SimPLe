# SimPLe PyTorch

Unofficial PyTorch implementation of the SimPLe algorithm for the Arcade Learning Environment's Atari 2600 games.

Based on the paper [Model-Based Reinforcement Learning for Atari](https://arxiv.org/abs/1903.00374).

- [Installation](#installation)
- [How to use](#how-to-use)
- [Stats](#stats)

![World model predictions on freeway](src/res/freeway_wm.gif)

*SimPLe predicting 46 frames in the future from 4 initial frames on FreewayDeterministic-v4.*

## Installation

This program requires **python 3.7** and uses **CUDA 10.2** if enabled.

### Using pip

- Run the following command to install the dependencies:
  ```shell script
  pip install torch==1.6.0 torchvision==0.7.0 tqdm==4.49.0 numpy==1.16.4
  
  git clone https://github.com/openai/baselines.git
  cd baselines
  pip install -e .
  ```

### Using conda

TODO

### Install wandb (optional)

You can use [wandb](https://www.wandb.com/) to track your experiments:
```shell script
pip install wandb==0.10.8
```

To use wandb, pass the flag `--use-wandb` when running the program. See [How to use](#how-to-use) for more details about flags.

## How to use

CUDA is enabled by default, see the following section to disable it.

To run the program, run the following command from the `src` directory:
```shell script
python simple.py
```

### Disable CUDA

To disable CUDA, pass the flag `--device cpu` to the command line. See the next section for more information about flags.

### Flags

You can pass multiple flags to the command line, a summary is printed at launch time.
The most useful flags are described in the following table:

| Flag | Value | Default | Description |
| ---- | ----- | ------- | ----------- |
| --agents | Any positive integer | 4 | The number of parallel environments to train the PPO agent on |
| --device | Any string accepted by [torch.device](https://pytorch.org/docs/stable/tensor_attributes.html#device-doc) | cuda | Sets the PyTorch's device |
| --env-name | Any string accepted by [gym.make](https://gym.openai.com/docs/#environments) | FreewayDeterministic-v4 | Sets the gym environment | 

The following boolean flags are set to `False` if not passed to the command line:

| Flag | Description |
| ---- | ----------- |
| --load-models | Loads models from `src/models/` and bypasses training |
| --render-training | Renders the environments during training |
| --save-models | Save the models after each epoch |
| --use-wandb | Enables [wandb](https://www.wandb.com/) to track the experiment |

For example, to run the program without CUDA and to render the environments during training, run:
```shell script
python simple.py --device cpu --render-training
```


## Stats

### Per environment performance

The scores* obtained with this implementation are detailed in the following table:

| Environment | Score | Paper's score | % of reported score in the original paper |
| ----------- | ---:  | ---:          | ---:                                      |
| FreewayDeterministic-v4 | 20.3 | 20.3 | 100.0% |
| KrullDeterministic-v4 | 3418.2 | 4539.9 | 82.6% |
| KungFuMasterDeterministic-v4 | N/A | 17257.2 | N/A |

**Scores obtained on only one full training per environment. More numbers to come.*

### Miscellaneous

- Using CUDA, training the agent and the models takes ~50h on a Nvidia GTX 1070 GPU
- Training the PPO agents on 4 agents requires 16Gb of RAM. If your machine runs out of memory, consider reducing the number of agents by passing the `--agents` flag 
- **In the original paper, 16 parallel agents are used. Use the flag** `--agents 16` **to replicate this.**
- This program was tested on Ubuntu 20.04.1 LTS