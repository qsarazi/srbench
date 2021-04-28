import pandas as pd
import numpy as np
from glob import glob
import argparse
import os, errno, sys
from joblib import Parallel, delayed
from seeds import SEEDS
from yaml import load, Loader


if __name__ == '__main__':
    # parse command line arguments
    parser = argparse.ArgumentParser(
            description="An analyst for quick ML applications.", add_help=False)
    parser.add_argument('DATASET_DIR', type=str,
                        help='Dataset directory like (pmlb/datasets)')    
    parser.add_argument('-h', '--help', action='help',
                        help='Show this help message and exit.')
    parser.add_argument('-ml', action='store', dest='LEARNERS',default=None,
            type=str, help='Comma-separated list of ML methods to use (should '
            'correspond to a py file name in methods/)')
    parser.add_argument('--local', action='store_true', dest='LOCAL', default=False, 
            help='Run locally as opposed to on LPC')
    parser.add_argument('-metric',action='store', dest='METRIC', default='f1_macro', 
            type=str, help='Metric to compare algorithms')
    parser.add_argument('-n_jobs',action='store',dest='N_JOBS',default=1,type=int,
            help='Number of parallel jobs')
    parser.add_argument('-n_trials',action='store',dest='N_TRIALS',default=1,
            type=int, help='Number of parallel jobs')
    parser.add_argument('-label',action='store',dest='LABEL',default='class',
            type=str,help='Name of class label column')
    parser.add_argument('-results',action='store',dest='RDIR',default='results',
            type=str,help='Results directory')
    parser.add_argument('-q',action='store',dest='QUEUE',
                        default='epistasis_long',
                        type=str,help='LSF queue')
    parser.add_argument('-m',action='store',dest='M',default=4096,type=int,
            help='LSF memory request and limit (MB)')
    parser.add_argument('-test',action='store_true', dest='TEST', 
                       help='Used for testing a minimal version')

    args = parser.parse_args()
     
    if args.LEARNERS == None:
        learners = [ml.split('/')[-1][:-3] for ml in glob('methods/*.py') 
                if not ml.split('/')[-1].startswith('_')]
    else:
        learners = [ml for ml in args.LEARNERS.split(',')]  # learners
    print('learners:',learners)

    print('dataset directory:',args.DATASET_DIR)


    # write run commands
    all_commands = []
    job_info=[]
    for dataset in glob(args.DATASET_DIR+'/*/*.tsv.gz'):
        # grab regression datasets
        metadata = load(
                open('/'.join(dataset.split('/')[:-1])+'/metadata.yaml','r'),
                Loader=Loader
        )
        if metadata['task'] != 'regression':
            continue
        
        dataname = dataset.split('/')[-1].split('.tsv.gz')[0]
        results_path = '/'.join([args.RDIR, dataname]) + '/'
        if not os.path.exists(results_path):
            os.makedirs(results_path)
        for t in range(args.N_TRIALS):
            # random_state = np.random.randint(2**15-1)
            random_state = SEEDS[t]
            print('random_seed:',random_state)
            
            for ml in learners:
                
                all_commands.append('python evaluate_model.py '
                                    '{DATASET}'
                                    ' -ml {ML}'
                                    ' -results_path {RDIR}'
                                    ' -seed {RS} {TEST}'.format(
                                        ML=ml,
                                        DATASET=dataset,
                                        RDIR=results_path,
                                        RS=random_state,
                                        TEST=('-test' if args.TEST
                                                else '')
                                        )
                                    )
                job_info.append({'ml':ml,
                                 'dataset':dataname,
                                 'seed':str(random_state),
                                 'results_path':results_path})

    if args.LOCAL:
        # run locally  
        for run_cmd in all_commands: 
            print(run_cmd)
            Parallel(n_jobs=args.N_JOBS)(delayed(os.system)(run_cmd) 
                                     for run_cmd in all_commands)
    else: # LPC
        for i,run_cmd in enumerate(all_commands):
            job_name = (job_info[i]['ml'] + '_' 
                        + job_info[i]['dataset'] 
                        + job_info[i]['seed'])
            out_file = job_info[i]['results_path'] + job_name + '_%J.out'
            error_file = out_file[:-4] + '.err'
            
            bsub_cmd = ('bsub -o {OUT_FILE} -n {N_CORES} -J {JOB_NAME} -q {QUEUE} '
                       '-R "span[hosts=1] rusage[mem={M}]" -M {M} ').format(
                               OUT_FILE=out_file,
                               JOB_NAME=job_name,
                               QUEUE=args.QUEUE,
                               N_CORES=args.N_JOBS,
                               M=args.M)
            
            bsub_cmd +=  '"' + run_cmd + '"'
            print(bsub_cmd)
            os.system(bsub_cmd)     # submit jobs 
