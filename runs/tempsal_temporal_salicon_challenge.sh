#!/bin/bash
#SBATCH --job-name=ttsc
#SBATCH --output=/scratch/izar/poletto/logs/log_tempsal_temporal_salicon_challenge_%j.out
#SBATCH --error=/scratch/izar/poletto/logs/log_tempsal_temporal_salicon_challenge_%j.err
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=2
#SBATCH --gres=gpu:2
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=2:00:00

module purge
module load gcc
module load python

source /home/poletto/venvs/pdm/bin/activate

cd /home/poletto/code
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
srun python src/tempsal/tempsal_train.py -c /home/poletto/code/config/tempsal/temporal_salicon_challenge.yml -n 2

