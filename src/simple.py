import os

import tensorflow as tf

tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)
from tqdm import trange
import argparse
from stable_baselines.common.vec_env import DummyVecEnv
from subproc_vec_env import SubprocVecEnv
import time
from next_frame_predictor import NextFramePredictor
from trainer import Trainer
from stable_baselines.common.policies import CnnPolicy
from atari_env import AtariEnv
from simulated_env import SimulatedEnv
from time import strftime
import torch
import numpy as np
from stable_baselines import PPO2


class SimPLe:

    def __init__(self, config):
        self.config = config
        self.real_env = AtariEnv(config, base_env_name=config.env_name)
        self.model = NextFramePredictor(config, self.real_env.action_space.n).to(config.device)
        self.trainer = Trainer(self.model, config)
        self.simulated_env = [
            SimulatedEnv.construct(config, self.real_env.action_space, i == 0) for i in range(config.agents)
        ]
        self.simulated_env = SubprocVecEnv(self.simulated_env, self.model, self.real_env.action_space.n, config)
        self.agent = PPO2(
            CnnPolicy,
            self.simulated_env,
            gamma=self.config.ppo_gamma,
            n_steps=self.config.rollout_length,
            nminibatches=5
        )

        if self.config.use_wandb:
            import wandb
            wandb.init(project='msth', name=self.config.experiment_name, config=config)
            wandb.watch(self.model)

    def set_agent_env(self, env):
        assert env == self.real_env or env == self.simulated_env
        if env == self.real_env:
            self.agent.set_env(DummyVecEnv((lambda: self.real_env,)))
        else:
            self.agent.set_env(self.simulated_env)
        # PPO2 is not updated properly with set_env, this fixes the issue
        self.agent.n_batch = self.agent.n_envs * self.agent.n_steps

    def train_agent_real_env(self):
        self.real_env.set_recording(True)
        self.real_env.new_epoch()
        self.set_agent_env(self.real_env)

        with trange(1, desc='Training agent in real env') as t:
            for _ in t:
                self.agent.learn(total_timesteps=6400)

        if self.config.save_models:
            self.agent.save(os.path.join('models', 'ppo'))

    def train_agent_sim_env(self, epoch):
        z = 1
        if epoch == 7 or epoch == 11:
            z = 2
        if epoch == 14:
            z = 3
        n = [1, 100, 1000][self.config.complexity]  # FIXME
        self.set_agent_env(self.simulated_env)

        # with trange(n * z * int(16 / self.config.agents), desc='Training agent in simulated env') as t:
        with trange(n * z, desc='Training agent in simulated env') as t:
            for _ in t:
                for i in range(self.config.agents):
                    # In the original paper, 1 agent out of 16 is trained on a deterministic start
                    # As using 16 agents requires resources, this condition accounts for this difference
                    test = float(torch.rand((1,))) < self.config.agents / 16
                    if i == self.config.agents - 1 and test:
                        initial_frames, initial_actions = self.real_env.get_first_small_rollout()
                    else:
                        sequence, actions, _, _, _ = self.real_env.sample_buffer()
                        index = int(torch.randint(len(sequence) - self.config.stacking, (1,)))
                        initial_frames = sequence[index:index + self.config.stacking]
                        initial_actions = actions[index:index + self.config.stacking]

                    self.simulated_env.env_method('restart', initial_frames, initial_actions, indices=i)

                self.agent.learn(total_timesteps=self.config.rollout_length * self.config.agents)

        if self.config.save_models:
            self.agent.save(os.path.join('models', 'ppo'))

    def evaluate_agent(self):
        if self.config.agent_evaluation_epochs < 1:
            return

        self.real_env.set_recording(False)
        self.set_agent_env(self.real_env)
        cum_rewards = []
        with trange(self.config.agent_evaluation_epochs, desc='Evaluating agent') as t:
            for _ in t:
                obs = self.real_env.reset()
                cum_reward = 0
                for _ in range(10000):
                    action = self.agent.predict(obs)[0]
                    obs, reward, done, _ = self.real_env.step(action, reduce_rewards=False)
                    if self.config.render_training:
                        self.real_env.render()
                    cum_reward += reward
                    if done:
                        break
                cum_rewards.append(cum_reward)
                t.set_postfix({'cum_reward': np.mean(cum_rewards)})

        if self.config.use_wandb:
            import wandb
            wandb.log({'cum_reward': np.mean(cum_rewards)})

    def load_model(self):
        self.model.load_state_dict(torch.load(os.path.join('models', 'model.pt')))
        self.model.stochastic_model.bits_predictor.load_state_dict(
            torch.load(os.path.join('models', 'bits_predictor.pt'))
        )
        self.model.reward_estimator.load_state_dict(torch.load(os.path.join('models', 'reward_model.pt')))
        self.model.value_estimator.load_state_dict(torch.load(os.path.join('models', 'value_model.pt')))
        self.agent = PPO2.load(os.path.join('models', 'ppo'))

    def train(self):
        self.train_agent_real_env()
        self.evaluate_agent()

        for epoch in trange(15, desc='Epoch'):
            self.trainer.train(epoch, self.real_env)
            self.train_agent_sim_env(epoch)
            self.evaluate_agent()
            self.train_agent_real_env()
            self.evaluate_agent()

        self.real_env.close()
        self.simulated_env.close()

    def test(self):
        while True:
            observation = self.real_env.reset()
            while True:
                action = self.agent.predict(observation)[0]
                observation, _, done, _ = self.real_env.step(action)
                self.real_env.render()
                time.sleep(1 / 60)
                if done:
                    break


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--agents', type=int, default=4)
    parser.add_argument('--agent-evaluation-epochs', type=int, default=10)
    parser.add_argument('--batch-size', type=int, default=4)
    parser.add_argument('--bottleneck-bits', type=int, default=128)
    parser.add_argument('--bottleneck-noise', type=float, default=0.1)
    parser.add_argument('--clip-grad-norm', type=float, default=1.0)
    parser.add_argument('--complexity', type=int, default=2)  # FIXME
    parser.add_argument('--compress-steps', type=int, default=5)
    parser.add_argument('--device', type=str, default='cuda')
    parser.add_argument('--dropout', type=float, default=0.15)
    parser.add_argument('--env-name', type=str, default='FreewayDeterministic-v4')
    parser.add_argument('--experiment-name', type=str, default=strftime('%d-%m-%y-%H:%M:%S'))
    parser.add_argument('--filter-double-steps', type=int, default=3)
    parser.add_argument('--frame-shape', type=int, nargs=3, default=(3, 105, 80))
    parser.add_argument('--hidden-layers', type=int, default=2)
    parser.add_argument('--hidden-size', type=int, default=96)
    parser.add_argument('--latent-rnn-max-sampling', type=float, default=0.5)
    parser.add_argument('--latent-state-size', type=int, default=128)
    parser.add_argument('--latent-use-max-probability', type=float, default=0.8)
    parser.add_argument('--load-models', default=False, action='store_true')
    parser.add_argument('--ppo-gamma', type=float, default=0.95)
    parser.add_argument('--recurrent-state-size', type=int, default=64)
    parser.add_argument('--render-training', default=False, action='store_true')
    parser.add_argument('--residual-dropout', type=float, default=0.5)
    parser.add_argument('--reward-model-batch-size', type=int, default=16)
    parser.add_argument('--rollout-length', type=int, default=50)
    parser.add_argument('--save-models', default=False, action='store_true')
    parser.add_argument('--scheduled-sampling-decay-steps', type=int, default=22250)
    parser.add_argument('--stacking', type=float, default=4)
    parser.add_argument('--target-loss-clipping', type=float, default=0.03)
    parser.add_argument('--use-wandb', default=False, action='store_true')
    parser.add_argument('--value-model-batch-size', type=int, default=16)
    config = parser.parse_args()

    args = vars(config)
    max_len = 0
    for arg in args:
        max_len = max(max_len, len(arg))
    for arg in args:
        value = str(getattr(config, arg))
        display = '{:<%i}: {}' % (max_len + 1)
        print(display.format(arg, value))

    simple = SimPLe(config)
    if config.load_models:
        simple.load_model()
    else:
        simple.train()
    simple.test()
