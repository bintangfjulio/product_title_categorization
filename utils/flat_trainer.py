import os
import torch
import random
import pandas as pd
import torch.nn as nn
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from statistics import mean
from tqdm import tqdm
from torchmetrics.classification import MulticlassAccuracy
from torchmetrics.classification import MulticlassF1Score
from models.bert_cnn import BERT_CNN

class Flat_Trainer(object):
    def __init__(self, tree, bert_model, seed, max_epochs, lr, dropout, patience):
        super(Flat_Trainer, self).__init__()
        np.random.seed(seed) 
        torch.manual_seed(seed)
        random.seed(seed)

        if torch.cuda.is_available():
            torch.cuda.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True

        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.tree = tree
        self.bert_model = bert_model
        self.max_epochs = max_epochs
        self.lr = lr
        self.dropout = dropout
        self.criterion = nn.CrossEntropyLoss()
        self.patience = patience
        self.checkpoint = None

    def scoring_result(self, preds, target):
        accuracy = self.accuracy_metric(preds, target)
        f1_micro = self.f1_micro_metric(preds, target)
        f1_macro = self.f1_macro_metric(preds, target)
        f1_weighted = self.f1_weighted_metric(preds, target)

        return accuracy, f1_micro, f1_macro, f1_weighted

    def initialize_model(self, num_classes):
        self.model = BERT_CNN(num_classes=num_classes, bert_model=self.bert_model, dropout=self.dropout)
        
        if self.checkpoint is not None:
            self.model.load_state_dict(self.checkpoint['model_state'])
            
        self.model.to(self.device)
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        self.scheduler = torch.optim.lr_scheduler.LinearLR(self.optimizer, start_factor=0.5, total_iters=5) 

        self.accuracy_metric = MulticlassAccuracy(num_classes=num_classes).to(self.device)
        self.f1_micro_metric = MulticlassF1Score(num_classes=num_classes, average='micro').to(self.device)
        self.f1_macro_metric = MulticlassF1Score(num_classes=num_classes, average='macro').to(self.device)
        self.f1_weighted_metric = MulticlassF1Score(num_classes=num_classes, average='weighted').to(self.device)

    def training_step(self):
        self.model.train(True)

        train_step_loss = []
        train_step_accuracy = []
        train_step_f1_micro = []
        train_step_f1_macro = []
        train_step_f1_weighted = []

        training_progress = tqdm(self.train_set)

        for train_batch in training_progress:
            input_ids, target = train_batch

            input_ids = input_ids.to(self.device)
            target = target.to(self.device)

            preds = self.model(input_ids=input_ids)
            loss = self.criterion(preds, target)
            preds = torch.argmax(preds, dim=1)

            accuracy, f1_micro, f1_macro, f1_weighted = self.scoring_result(preds=preds, target=target)

            train_step_loss.append(loss.item())
            train_step_accuracy.append(accuracy.item())
            train_step_f1_micro.append(f1_micro.item())
            train_step_f1_macro.append(f1_macro.item())
            train_step_f1_weighted.append(f1_weighted.item())
            
            training_progress.set_description("Train Step Loss : " + str(round(loss.item(), 2)) + 
                                        " | Train Step Accuracy : " + str(round(accuracy.item(), 2)) + 
                                        " | Train Step F1 Micro : " + str(round(f1_micro.item(), 2)) +
                                        " | Train Step F1 Weighted : " + str(round(f1_weighted.item(), 2)) +
                                        " | Train Step F1 Macro : " + str(round(f1_macro.item(), 2)))

            loss.backward()
            self.optimizer.step()
            self.scheduler.step()
            self.model.zero_grad()

        print("On Epoch Train Loss: ", round(mean(train_step_loss), 2))
        print("On Epoch Train Accuracy: ", round(mean(train_step_accuracy), 2))
        print("On Epoch Train F1 Micro: ", round(mean(train_step_f1_micro), 2))
        print("On Epoch Train F1 Macro: ", round(mean(train_step_f1_macro), 2))
        print("On Epoch Train F1 Weighted: ", round(mean(train_step_f1_weighted), 2))

        return mean(train_step_loss), mean(train_step_accuracy), mean(train_step_f1_micro), mean(train_step_f1_macro), mean(train_step_f1_weighted)

    def validation_step(self):
        self.model.eval()

        val_step_loss = []
        val_step_accuracy = []
        val_step_f1_micro = []
        val_step_f1_macro = []
        val_step_f1_weighted = []

        with torch.no_grad():
            validation_progress = tqdm(self.valid_set)

            for valid_batch in validation_progress:
                input_ids, target = valid_batch

                input_ids = input_ids.to(self.device)
                target = target.to(self.device)

                preds = self.model(input_ids=input_ids)
                loss = self.criterion(preds, target)
                preds = torch.argmax(preds, dim=1)

                accuracy, f1_micro, f1_macro, f1_weighted = self.scoring_result(preds=preds, target=target)

                val_step_loss.append(loss.item())
                val_step_accuracy.append(accuracy.item())
                val_step_f1_micro.append(f1_micro.item())
                val_step_f1_macro.append(f1_macro.item())
                val_step_f1_weighted.append(f1_weighted.item())
                
                validation_progress.set_description("Validation Step Loss : " + str(round(loss.item(), 2)) + 
                                            " | Validation Step Accuracy : " + str(round(accuracy.item(), 2)) + 
                                            " | Validation Step F1 Micro : " + str(round(f1_micro.item(), 2)) +
                                            " | Validation Step F1 Weighted : " + str(round(f1_weighted.item(), 2)) +
                                            " | Validation Step F1 Macro : " + str(round(f1_macro.item(), 2)))
            
                self.model.zero_grad()

        print("On Epoch Validation Loss: ", round(mean(val_step_loss), 2))
        print("On Epoch Validation Accuracy: ", round(mean(val_step_accuracy), 2))
        print("On Epoch Validation F1 Micro: ", round(mean(val_step_f1_micro), 2))
        print("On Epoch Validation F1 Macro: ", round(mean(val_step_f1_macro), 2))
        print("On Epoch Validation F1 Weighted: ", round(mean(val_step_f1_weighted), 2))

        return mean(val_step_loss), mean(val_step_accuracy), mean(val_step_f1_micro), mean(val_step_f1_macro), mean(val_step_f1_weighted)
    
    def test_step(self):
        self.model.eval()

        test_step_loss = []
        test_step_accuracy = []
        test_step_f1_micro = []
        test_step_f1_macro = []
        test_step_f1_weighted = []

        with torch.no_grad():
            test_progress = tqdm(self.test_set)

            for test_batch in test_progress:
                input_ids, target = test_batch

                input_ids = input_ids.to(self.device)
                target = target.to(self.device)

                preds = self.model(input_ids=input_ids)
                loss = self.criterion(preds, target)
                preds = torch.argmax(preds, dim=1)

                accuracy, f1_micro, f1_macro, f1_weighted = self.scoring_result(preds=preds, target=target)

                test_step_loss.append(loss.item())
                test_step_accuracy.append(accuracy.item())
                test_step_f1_micro.append(f1_micro.item())
                test_step_f1_macro.append(f1_macro.item())
                test_step_f1_weighted.append(f1_weighted.item())
                
                test_progress.set_description("Test Step Loss : " + str(round(loss.item(), 2)) + 
                                            " | Test Step Accuracy : " + str(round(accuracy.item(), 2)) + 
                                            " | Test Step F1 Micro : " + str(round(f1_micro.item(), 2)) +
                                            " | Test Step F1 Weighted : " + str(round(f1_weighted.item(), 2)) +
                                            " | Test Step F1 Macro : " + str(round(f1_macro.item(), 2)))

        print("On Epoch Test Loss: ", round(mean(test_step_loss), 2))
        print("On Epoch Test Accuracy: ", round(mean(test_step_accuracy), 2))
        print("On Epoch Test F1 Micro: ", round(mean(test_step_f1_micro), 2))
        print("On Epoch Test F1 Macro: ", round(mean(test_step_f1_macro), 2))
        print("On Epoch Test F1 Weighted: ", round(mean(test_step_f1_weighted), 2))

        return mean(test_step_loss), mean(test_step_accuracy), mean(test_step_f1_micro), mean(test_step_f1_macro), mean(test_step_f1_weighted)
    
    def fit(self, datamodule):
        level_on_nodes, _, _, _ = self.tree.get_hierarchy()

        train_accuracy_epoch = []
        train_loss_epoch = []
        train_f1_micro_epoch = []
        train_f1_macro_epoch = []
        train_f1_weighted_epoch = []
        train_epoch = []

        val_accuracy_epoch = []
        val_loss_epoch = []
        val_f1_micro_epoch = []
        val_f1_macro_epoch = []
        val_f1_weighted_epoch = []
        val_epoch = []

        self.train_set, self.valid_set = datamodule.flat_dataloader(stage='fit', tree=self.tree)
        self.initialize_model(num_classes=len(level_on_nodes[len(level_on_nodes) - 1]))
        self.model.zero_grad()

        best_loss = 9.99
        fail = 0

        for epoch in range(self.max_epochs):
            if fail == self.patience:
                break
                
            print("Training Stage...")
            print("Epoch ", epoch)
            print("=" * 50)

            train_loss, train_accuracy, train_f1_micro, train_f1_macro, train_f1_weighted = self.training_step()

            train_loss_epoch.append(train_loss)
            train_accuracy_epoch.append(train_accuracy)
            train_f1_micro_epoch.append(train_f1_micro)
            train_f1_macro_epoch.append(train_f1_macro)
            train_f1_weighted_epoch.append(train_f1_weighted)
            train_epoch.append(epoch)

            print("Validation Stage...")
            print("=" * 50)

            val_loss, val_accuracy, val_f1_micro, val_f1_macro, val_f1_weighted = self.validation_step()

            val_loss_epoch.append(val_loss)
            val_accuracy_epoch.append(val_accuracy)
            val_f1_micro_epoch.append(val_f1_micro)
            val_f1_macro_epoch.append(val_f1_macro)
            val_f1_weighted_epoch.append(val_f1_weighted)
            val_epoch.append(epoch)

            if round(val_loss, 2) < round(best_loss, 2):
                if not os.path.exists('checkpoints/flat_result'):
                    os.makedirs('checkpoints/flat_result')

                if os.path.exists('checkpoints/flat_result/flat_temp.pt'):
                    os.remove('checkpoints/flat_result/flat_temp.pt')

                checkpoint = {
                    "epoch": epoch,
                    "model_state": self.model.state_dict(),
                }
                    
                torch.save(checkpoint, 'checkpoints/flat_result/flat_temp.pt')
                best_loss = val_loss
                fail = 0

            else:
                fail += 1

        if not os.path.exists('logs/flat_result'):
            os.makedirs('logs/flat_result')
            
        train_result = pd.DataFrame({'epoch': train_epoch, 'accuracy': train_accuracy_epoch, 'loss': train_loss_epoch, 'f1_micro': train_f1_micro_epoch, 'f1_macro': train_f1_macro_epoch, 'f1_weighted': train_f1_weighted_epoch})
        valid_result = pd.DataFrame({'epoch': val_epoch, 'accuracy': val_accuracy_epoch, 'loss': val_loss_epoch, 'f1_micro': val_f1_micro_epoch, 'f1_macro': val_f1_macro_epoch, 'f1_weighted': val_f1_weighted_epoch})
        
        train_result.to_csv('logs/flat_result/train_result.csv', index=False, encoding='utf-8')
        valid_result.to_csv('logs/flat_result/valid_result.csv', index=False, encoding='utf-8')

    def test(self, datamodule):
        level_on_nodes, _, _, _ = self.tree.get_hierarchy()
        
        test_accuracy_epoch = []
        test_loss_epoch = []
        test_f1_micro_epoch = []
        test_f1_macro_epoch = []
        test_f1_weighted_epoch = []

        self.test_set = datamodule.flat_dataloader(stage='test', tree=self.tree)
        self.checkpoint = torch.load('checkpoints/flat_result/flat_temp.pt')
        self.initialize_model(num_classes=len(level_on_nodes[len(level_on_nodes) - 1]))
        self.model.zero_grad()
        
        print("Test Stage...")
        print("Loading Checkpoint on Epoch", self.checkpoint['epoch'])
        print("=" * 50)

        test_loss, test_accuracy, test_f1_micro, test_f1_macro, test_f1_weighted = self.test_step()
        
        test_loss_epoch.append(test_loss)
        test_accuracy_epoch.append(test_accuracy)
        test_f1_micro_epoch.append(test_f1_micro)
        test_f1_macro_epoch.append(test_f1_macro)
        test_f1_weighted_epoch.append(test_f1_weighted)

        if not os.path.exists('logs/flat_result'):
            os.makedirs('logs/flat_result')
                        
        test_result = pd.DataFrame({'accuracy': test_accuracy_epoch, 'loss': test_loss_epoch, 'f1_micro': test_f1_micro_epoch, 'f1_macro': test_f1_macro_epoch, 'f1_weighted': test_f1_weighted_epoch})
        test_result.to_csv('logs/flat_result/test_result.csv', index=False, encoding='utf-8')

    def create_graph(self):
        pd.options.display.float_format = '{:,.2f}'.format        
        train_log = pd.read_csv('logs/flat_result/train_result.csv')
        valid_log = pd.read_csv('logs/flat_result/valid_result.csv')

        for metric in ['accuracy', 'loss', 'f1_micro', 'f1_macro', 'f1_weighted']:
            plt.xlabel('Epoch')
            label = metric.replace("_", " ").title()
            plt.ylabel(label)
            plt.plot(train_log['epoch'], train_log[metric], marker='o', label='Train')
            plt.plot(valid_log['epoch'], valid_log[metric], marker='o', label='Validation')
            plt.gca().xaxis.set_major_locator(mticker.MultipleLocator(1))
            
            if metric == 'loss':
                best_train = round(train_log[metric].min(), 2)
                best_val = round(valid_log[metric].min(), 2)

            else:
                best_train = round(train_log[metric].max() * 100, 2)
                best_val = round(valid_log[metric].max() * 100, 2)

            plt.figtext(.5, .91, f'Best Flat Model Train {label}: {best_train}%\nBest Flat Model Validation {label}: {best_val}%', fontsize='medium', ha='center')

            for stage, data_stage in enumerate([train_log[metric], valid_log[metric]]):
                for x_epoch, y_sc in enumerate(data_stage):
                    y_sc_lbl = '{:.2f}'.format(y_sc)

                    plt.annotate(y_sc_lbl,
                                (x_epoch, y_sc),
                                textcoords='offset points',
                                xytext=(0, 4),
                                fontsize='small',
                                ha='right' if stage == 0 else 'left')
                    
            plt.legend()
            plt.savefig(f'logs/flat_result/flat_{metric}_graph')
            plt.clf()